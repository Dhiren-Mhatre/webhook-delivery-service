import os
import logging
from flask import Flask, request, render_template, jsonify, redirect, url_for, flash, current_app
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_caching import Cache
import json
import hmac
import hashlib
import requests
from datetime import datetime, timedelta

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_pyfile('config.py')
app.secret_key = os.environ.get("SESSION_SECRET", app.config['SECRET_KEY'])
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

cache = Cache(app, config={
    'CACHE_TYPE': 'SimpleCache',
    'CACHE_DEFAULT_TIMEOUT': 300
})

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
db.init_app(app)

with app.app_context():
    from models import Subscription, WebhookDelivery, DeliveryAttempt
    db.create_all()

@app.context_processor
def inject_context():
    """Inject common variables into all templates"""
    context = {'now': datetime.now()}
    
    try:
        context['subscriptions'] = Subscription.query.all()
    except:
        context['subscriptions'] = []
        
    return context

@app.route('/')
def index():
    """Landing page showing service overview"""
    from sqlalchemy import func
    
    subscriptions_count = Subscription.query.count()
    
    total_deliveries = WebhookDelivery.query.count()
    
    status_counts = {}
    status_percentages = {}
    
    for status in ['pending', 'processing', 'delivered', 'failed']:
        count = WebhookDelivery.query.filter_by(status=status).count()
        status_counts[status] = count
    
    total_status = sum(status_counts.values())
    if total_status > 0:
        for status, count in status_counts.items():
            status_percentages[f"{status}_percent"] = round((count / total_status) * 100)
    else:
        for status in status_counts:
            status_percentages[f"{status}_percent"] = 0
    
    successful_deliveries = status_counts.get('delivered', 0)
    success_rate = round((successful_deliveries / total_deliveries * 100) if total_deliveries > 0 else 0)
    
    avg_attempts_result = db.session.query(
        func.avg(
            db.session.query(func.count(DeliveryAttempt.id))
            .filter(DeliveryAttempt.delivery_id == WebhookDelivery.id)
            .correlate(WebhookDelivery)
            .scalar_subquery()
        )
    ).scalar()
    
    avg_attempts = round(float(avg_attempts_result or 0), 1)
    
    stats = {
        'subscriptions': subscriptions_count,
        'total_deliveries': total_deliveries,
        'success_rate': success_rate,
        'avg_attempts': avg_attempts,
        'status_breakdown': {**status_counts, **status_percentages}
    }
    
    recent_deliveries = WebhookDelivery.query.order_by(WebhookDelivery.created_at.desc()).limit(5).all()
    
    return render_template('index.html', stats=stats, recent_deliveries=recent_deliveries)

@app.route('/subscriptions')
def list_subscriptions():
    """List all subscriptions"""
    subscriptions = Subscription.query.all()
    return render_template('subscriptions.html', subscriptions=subscriptions)

@app.route('/subscriptions/new', methods=['GET', 'POST'])
def create_subscription():
    """Create a new subscription"""
    if request.method == 'POST':
        name = request.form.get('name', '')
        target_url = request.form.get('target_url')
        secret = request.form.get('secret', '')
        status = 'active' if request.form.get('status') == 'active' else 'inactive'
        
        if not target_url:
            flash('Target URL is required', 'danger')
            return redirect(url_for('create_subscription'))
        
        event_types = request.form.getlist('event_types')
        
        subscription = Subscription(
            name=name,
            target_url=target_url,
            secret=secret,
            event_types=event_types if event_types else None,
            status=status
        )
        db.session.add(subscription)
        db.session.commit()
        
        flash('Subscription created successfully', 'success')
        return redirect(url_for('list_subscriptions'))
    
    return render_template('subscriptions.html', action='create')

@app.route('/subscriptions/<int:subscription_id>')
def view_subscription(subscription_id):
    """View subscription details and recent deliveries"""
    from sqlalchemy import func
    
    subscription = Subscription.query.get_or_404(subscription_id)
    
    # Get recent deliveries for this subscription
    recent_deliveries = WebhookDelivery.query.filter_by(subscription_id=subscription_id)\
                          .order_by(WebhookDelivery.created_at.desc())\
                          .limit(20).all()
    
    # Get delivery statistics for this subscription
    total_deliveries = WebhookDelivery.query.filter_by(subscription_id=subscription_id).count()
    
    # Success rate calculation
    successful_deliveries = WebhookDelivery.query.filter_by(
        subscription_id=subscription_id, 
        status='delivered'
    ).count()
    
    success_rate = round((successful_deliveries / total_deliveries * 100) if total_deliveries > 0 else 0)
    
    # Average attempts per delivery
    avg_attempts_result = db.session.query(
        func.avg(
            db.session.query(func.count(DeliveryAttempt.id))
            .join(WebhookDelivery, DeliveryAttempt.delivery_id == WebhookDelivery.id)
            .filter(WebhookDelivery.subscription_id == subscription_id)
            .group_by(DeliveryAttempt.delivery_id)
            .scalar_subquery()
        )
    ).scalar()
    
    avg_attempts = round(float(avg_attempts_result or 0), 1)
    
    # Prepare stats dictionary
    stats = {
        'total': total_deliveries,
        'successful': successful_deliveries,
        'success_rate': success_rate,
        'avg_attempts': avg_attempts
    }
    
    return render_template('subscription_detail.html', 
                          subscription=subscription, 
                          recent_deliveries=recent_deliveries,
                          stats=stats)

@app.route('/subscriptions/<int:subscription_id>/edit', methods=['GET', 'POST'])
def edit_subscription(subscription_id):
    """Edit an existing subscription"""
    subscription = Subscription.query.get_or_404(subscription_id)
    
    if request.method == 'POST':
        name = request.form.get('name', '')
        target_url = request.form.get('target_url')
        secret = request.form.get('secret', '')
        status = 'active' if request.form.get('status') == 'active' else 'inactive'
        
        if not target_url:
            flash('Target URL is required', 'danger')
            return redirect(url_for('edit_subscription', subscription_id=subscription_id))
        
        # Get event types from checkboxes (multiselect)
        event_types = request.form.getlist('event_types')
        
        subscription.name = name
        subscription.target_url = target_url
        subscription.secret = secret
        subscription.event_types = event_types if event_types else None
        subscription.status = status
        
        db.session.commit()
        
        # Invalidate cache
        cache.delete(f'subscription_{subscription_id}')
        
        flash('Subscription updated successfully', 'success')
        return redirect(url_for('view_subscription', subscription_id=subscription_id))
    
    return render_template('subscriptions.html', 
                          action='edit', 
                          subscription=subscription)

@app.route('/subscriptions/<int:subscription_id>/delete', methods=['POST'])
def delete_subscription(subscription_id):
    """Delete a subscription"""
    subscription = Subscription.query.get_or_404(subscription_id)
    
    db.session.delete(subscription)
    db.session.commit()
    
    # Invalidate cache
    cache.delete(f'subscription_{subscription_id}')
    
    flash('Subscription deleted successfully', 'success')
    return redirect(url_for('list_subscriptions'))

@app.route('/deliveries')
@app.route('/deliveries/<int:subscription_id>')
def deliveries(subscription_id=None):
    """View all deliveries with optional subscription filter"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Base query with optional subscription filter
    query = WebhookDelivery.query
    if subscription_id:
        query = query.filter_by(subscription_id=subscription_id)
    
    # Paginate results
    pagination = query.order_by(WebhookDelivery.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    deliveries = pagination.items
    
    # Get all subscriptions for the filter dropdown
    subscriptions = Subscription.query.all()
    
    return render_template('deliveries.html',
                          deliveries=deliveries,
                          subscriptions=subscriptions,
                          filter_subscription=subscription_id,
                          page=page,
                          has_next_page=pagination.has_next)

@app.route('/delivery/<uuid:delivery_id>')
def view_delivery(delivery_id):
    """View delivery details and its attempts"""
    delivery = WebhookDelivery.query.get_or_404(str(delivery_id))
    attempts = DeliveryAttempt.query.filter_by(delivery_id=str(delivery_id))\
                .order_by(DeliveryAttempt.attempt_number).all()
    subscription = Subscription.query.get(delivery.subscription_id)
    
    return render_template('delivery_status.html', 
                          delivery=delivery, 
                          subscription=subscription,
                          attempts=attempts,
                          payload=json.dumps(delivery.payload, indent=2))

# API Routes
@app.route('/api/subscriptions', methods=['GET'])
def api_list_subscriptions():
    """API to list all subscriptions"""
    subscriptions = Subscription.query.all()
    return jsonify({
        'subscriptions': [sub.to_dict() for sub in subscriptions]
    })

@app.route('/api/subscriptions', methods=['POST'])
def api_create_subscription():
    """API to create a new subscription"""
    data = request.json
    
    if not data or 'target_url' not in data:
        return jsonify({'error': 'Target URL is required'}), 400
    
    subscription = Subscription(
        name=data.get('name', ''),
        target_url=data['target_url'],
        secret=data.get('secret', ''),
        event_types=data.get('event_types'),
        status=data.get('status', 'active')
    )
    
    db.session.add(subscription)
    db.session.commit()
    
    return jsonify({
        'message': 'Subscription created successfully',
        'subscription': subscription.to_dict()
    }), 201

@app.route('/api/subscriptions/<int:subscription_id>', methods=['GET'])
def api_get_subscription(subscription_id):
    """API to get subscription details"""
    subscription = Subscription.query.get_or_404(subscription_id)
    return jsonify({
        'subscription': subscription.to_dict()
    })

@app.route('/api/subscriptions/<int:subscription_id>', methods=['PUT'])
def api_update_subscription(subscription_id):
    """API to update a subscription"""
    subscription = Subscription.query.get_or_404(subscription_id)
    data = request.json
    
    if 'name' in data:
        subscription.name = data['name']
    if 'target_url' in data:
        subscription.target_url = data['target_url']
    if 'secret' in data:
        subscription.secret = data['secret']
    if 'event_types' in data:
        subscription.event_types = data['event_types']
    if 'status' in data:
        subscription.status = data['status']
    
    db.session.commit()
    
    # Invalidate cache
    cache.delete(f'subscription_{subscription_id}')
    
    return jsonify({
        'message': 'Subscription updated successfully',
        'subscription': subscription.to_dict()
    })

@app.route('/api/subscriptions/<int:subscription_id>', methods=['DELETE'])
def api_delete_subscription(subscription_id):
    """API to delete a subscription"""
    subscription = Subscription.query.get_or_404(subscription_id)
    
    db.session.delete(subscription)
    db.session.commit()
    
    # Invalidate cache
    cache.delete(f'subscription_{subscription_id}')
    
    return jsonify({
        'message': 'Subscription deleted successfully'
    })


@app.route('/api/ingest/<int:subscription_id>', methods=['POST'])
def ingest_webhook(subscription_id):
    """Ingest a webhook for a specific subscription"""
    try:
        # Get subscription directly from the database
        subscription = Subscription.query.get_or_404(subscription_id)
        
        # Get the webhook payload
        payload = request.json
        if not payload:
            return jsonify({'error': 'No payload provided'}), 400
        
        # Check if event type filtering is enabled and apply it
        event_type = request.headers.get('X-Event-Type') or request.args.get('event_type')
        
        # Only filter if subscription has event types configured and is in active status
        if subscription.status == 'active' and subscription.event_types and event_type:
            if event_type not in subscription.event_types:
                current_app.logger.warning(f"Subscription {subscription_id} does not accept events of type: {event_type}")
                return jsonify({
                    'message': f'Subscription does not accept events of type: {event_type}',
                    'status': 'rejected'
                }), 202  # Accepted but not processed
        
        # If secret is present, verify signature
        if subscription.secret:
            signature_header = request.headers.get('X-Hub-Signature-256')
            if not signature_header:
                return jsonify({'error': 'Missing signature header'}), 401
            
            # Calculate expected signature
            payload_bytes = json.dumps(payload).encode('utf-8')
            expected_signature = 'sha256=' + hmac.new(
                subscription.secret.encode('utf-8'),
                payload_bytes,
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature_header, expected_signature):
                return jsonify({'error': 'Invalid signature'}), 401
        
        # Create a new webhook delivery record
        delivery = WebhookDelivery(
            subscription_id=subscription_id,
            payload=payload,
            event_type=event_type
        )
        db.session.add(delivery)
        db.session.commit()
        
        # Check if we're running on Render or if Celery is not available
        # This prioritizes direct processing on Render to avoid webhooks being stuck in pending
        process_directly = True
        
        # If not on Render, try to use Celery
        if 'RENDER' not in os.environ:
            try:
                # Import task function here to avoid circular import
                from tasks import process_webhook
                
                # Try to queue the webhook for processing using Celery
                process_webhook.delay(str(delivery.id))
                process_directly = False
                current_app.logger.info(f"Queued webhook {delivery.id} for processing by Celery")
            except Exception as e:
                current_app.logger.warning(f"Failed to queue webhook with Celery: {str(e)}. Processing directly.")
                process_directly = True
        else:
            current_app.logger.info("Running on Render. Processing webhook directly.")
        
        # Process webhook directly if needed (on Render or if Celery failed)
        if process_directly:
            # Update status to processing
            delivery.status = 'processing'
            db.session.commit()
            
            # Attempt to deliver the webhook
            attempt_number = 1
            
            # Create a delivery attempt record
            attempt = DeliveryAttempt(
                delivery_id=delivery.id,
                attempt_number=attempt_number,
                status='failed',  # Default to failed, update on success
            )
            
            try:
                # Prepare headers
                headers = {
                    'Content-Type': 'application/json',
                    'User-Agent': 'Webhook-Delivery-Service/1.0',
                    'X-Webhook-ID': str(delivery.id),
                    'X-Webhook-Attempt': str(attempt_number)
                }
                
                # Add event type if available
                if delivery.event_type:
                    headers['X-Event-Type'] = delivery.event_type
                
                # Add signature if secret is configured
                if subscription.secret:
                    payload_bytes = json.dumps(payload).encode('utf-8')
                    signature = hmac.new(
                        subscription.secret.encode('utf-8'),
                        payload_bytes,
                        hashlib.sha256
                    ).hexdigest()
                    headers['X-Hub-Signature-256'] = f"sha256={signature}"
                
                # Make the POST request with timeout
                timeout = app.config.get('DELIVERY_TIMEOUT', 10)
                response = requests.post(
                    subscription.target_url,
                    json=payload,
                    headers=headers,
                    timeout=timeout
                )
                
                # Record the response details
                attempt.status_code = response.status_code
                
                # Limit response body size to avoid storing very large responses
                response_body = response.text[:1000]
                if len(response.text) > 1000:
                    response_body += '... [truncated]'
                attempt.response_body = response_body
                
                # Check if successful (2xx response)
                if 200 <= response.status_code < 300:
                    attempt.status = 'success'
                    delivery.status = 'delivered'
                else:
                    attempt.error_details = f"HTTP error: {response.status_code}"
                    delivery.status = 'failed'
            
            except requests.Timeout:
                attempt.error_details = f"Request timed out after {timeout} seconds"
                delivery.status = 'failed'
            
            except requests.ConnectionError as e:
                attempt.error_details = f"Connection error: {str(e)}"
                delivery.status = 'failed'
            
            except Exception as e:
                attempt.error_details = f"Unexpected error: {str(e)}"
                delivery.status = 'failed'
            
            # Save the attempt and update delivery
            db.session.add(attempt)
            delivery.completed_at = datetime.now()
            db.session.commit()
            
            current_app.logger.info(f"Direct webhook delivery completed with status: {delivery.status}")
        
        return jsonify({
            'message': 'Webhook accepted for delivery',
            'delivery_id': str(delivery.id)
        }), 202  # Accepted for processing
    
    except Exception as e:
        # Catch all exceptions and return as JSON
        current_app.logger.error(f"Error in webhook ingestion: {str(e)}")
        return jsonify({
            'error': f'Server error: {str(e)}'
        }), 500

@app.route('/api/delivery/<uuid:delivery_id>', methods=['GET'])
def api_delivery_status(delivery_id):
    """API to get the status of a webhook delivery"""
    delivery = WebhookDelivery.query.get_or_404(str(delivery_id))
    attempts = DeliveryAttempt.query.filter_by(delivery_id=str(delivery_id))\
                .order_by(DeliveryAttempt.attempt_number).all()
    
    return jsonify({
        'delivery': delivery.to_dict(),
        'attempts': [attempt.to_dict() for attempt in attempts]
    })

@app.route('/api/subscriptions/<int:subscription_id>/deliveries', methods=['GET'])
def api_subscription_deliveries(subscription_id):
    """API to get recent deliveries for a subscription"""
    subscription = Subscription.query.get_or_404(subscription_id)
    
    limit = request.args.get('limit', 20, type=int)
    if limit > 100:
        limit = 100  # Cap the limit to prevent abuse
    
    deliveries = WebhookDelivery.query.filter_by(subscription_id=subscription_id)\
                  .order_by(WebhookDelivery.created_at.desc())\
                  .limit(limit).all()
    
    return jsonify({
        'subscription_id': subscription_id,
        'deliveries': [delivery.to_dict() for delivery in deliveries]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)