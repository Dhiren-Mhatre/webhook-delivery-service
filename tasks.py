import json
import logging
import requests
import time
import os
import sys
from datetime import datetime, timedelta
from flask import current_app
from contextlib import contextmanager
from celery_app import celery_app

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@contextmanager
def app_context():
    """Context manager to provide Flask app context for Celery tasks"""
    # Add current directory to Python path to help with imports
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    # Now import the app
    from app import app
    with app.app_context():
        yield

@celery_app.task(bind=True, max_retries=None)
def process_webhook(self, delivery_id):
    """Process a webhook delivery with retries"""
    with app_context():
        logger.info(f"Processing webhook delivery: {delivery_id}")
        
        # Import models here to avoid circular imports
        from app import app, db, cache
        from models import Subscription, WebhookDelivery, DeliveryAttempt
        
        delivery = WebhookDelivery.query.get(delivery_id)
        if not delivery:
            logger.error(f"Delivery not found: {delivery_id}")
            return {"error": "Delivery not found"}
        
        # Update status to processing
        delivery.status = 'processing'
        db.session.commit()
        
        # Get subscription from cache or database
        subscription = cache.get(f'subscription_{delivery.subscription_id}')
        if subscription is None:
            subscription = Subscription.query.get(delivery.subscription_id)
            if not subscription:
                logger.error(f"Subscription not found: {delivery.subscription_id}")
                delivery.status = 'failed'
                db.session.commit()
                return {"error": "Subscription not found"}
            cache.set(f'subscription_{delivery.subscription_id}', subscription)
        
        # Get the current attempt number
        current_attempt = DeliveryAttempt.query.filter_by(delivery_id=delivery_id).count() + 1
        
        # Check if maximum retries reached
        max_retries = app.config['MAX_RETRY_ATTEMPTS']
        if current_attempt > max_retries:
            logger.warning(f"Maximum retry attempts reached for delivery: {delivery_id}")
            delivery.status = 'failed'
            delivery.completed_at = datetime.utcnow()
            db.session.commit()
            return {"status": "failed", "reason": "Maximum retry attempts reached"}
        
        # Attempt delivery
        attempt_result = attempt_delivery(delivery, subscription, current_attempt)
        
        # If success, update delivery status
        if attempt_result['status'] == 'success':
            delivery.status = 'delivered'
            delivery.completed_at = datetime.utcnow()
            db.session.commit()
            return {"status": "delivered"}
        
        # If failure, schedule retry with exponential backoff
        retry_delays = app.config['RETRY_DELAYS']
        retry_index = min(current_attempt - 1, len(retry_delays) - 1)
        retry_delay = retry_delays[retry_index]
        
        logger.info(f"Scheduling retry {current_attempt + 1} for delivery {delivery_id} in {retry_delay} seconds")
        self.retry(countdown=retry_delay)
        
        return {"status": "retry_scheduled", "attempt": current_attempt, "next_retry_in": retry_delay}

def attempt_delivery(delivery, subscription, attempt_number):
    """Attempt to deliver a webhook to its target URL"""
    # Import models and app here to avoid circular imports
    from app import app, db
    from models import DeliveryAttempt
    
    logger.info(f"Attempt {attempt_number} for delivery: {str(delivery.id)}")
    
    # Create a delivery attempt record
    attempt = DeliveryAttempt(
        delivery_id=delivery.id,
        attempt_number=attempt_number,
        status='failed',  # Default to failed, update on success
    )
    
    try:
        # Get the payload and prepare headers
        payload = delivery.payload
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Webhook-Delivery-Service/1.0',
            'X-Webhook-ID': str(delivery.id),
            'X-Webhook-Attempt': str(attempt_number)
        }
        
        # Add event type if available
        if delivery.event_type:
            headers['X-Event-Type'] = delivery.event_type
        
        # Make the POST request with timeout
        timeout = app.config['DELIVERY_TIMEOUT']
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
            result = {
                'status': 'success',
                'status_code': response.status_code
            }
        else:
            attempt.error_details = f"HTTP error: {response.status_code}"
            result = {
                'status': 'failed',
                'reason': 'non-2xx-response',
                'status_code': response.status_code
            }
    
    except requests.Timeout:
        attempt.error_details = f"Request timed out after {timeout} seconds"
        result = {
            'status': 'failed',
            'reason': 'timeout'
        }
    
    except requests.ConnectionError as e:
        attempt.error_details = f"Connection error: {str(e)}"
        result = {
            'status': 'failed',
            'reason': 'connection_error'
        }
    
    except Exception as e:
        attempt.error_details = f"Unexpected error: {str(e)}"
        result = {
            'status': 'failed',
            'reason': 'unexpected_error'
        }
    
    # Save the attempt
    db.session.add(attempt)
    db.session.commit()
    
    return result

@celery_app.task
def cleanup_old_delivery_logs():
    """Clean up delivery logs older than the retention period"""
    with app_context():
        # Import app and models here to avoid circular imports
        from app import app, db
        from models import WebhookDelivery
        
        retention_hours = app.config['LOG_RETENTION_PERIOD']
        cutoff_date = datetime.utcnow() - timedelta(hours=retention_hours)
        
        logger.info(f"Cleaning up delivery logs older than {cutoff_date}")
        
        # Find old deliveries
        old_deliveries = WebhookDelivery.query.filter(
            WebhookDelivery.created_at < cutoff_date
        ).all()
        
        # Delete them and their attempts
        for delivery in old_deliveries:
            # No need to manually delete attempts due to cascade delete
            db.session.delete(delivery)
        
        db.session.commit()
        
        logger.info(f"Cleaned up {len(old_deliveries)} old delivery logs")
        
        return {"status": "success", "deleted_count": len(old_deliveries)}