import unittest
import json
import uuid
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from app import app, db
from models import Subscription, WebhookDelivery, DeliveryAttempt
from tasks import cleanup_old_delivery_logs, attempt_delivery

class WebhookDeliveryServiceTestCase(unittest.TestCase):
    def setUp(self):
        """Set up test environment"""
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app = app.test_client()
        
        with app.app_context():
            db.create_all()
    
    def tearDown(self):
        """Clean up after tests"""
        with app.app_context():
            db.session.remove()
            db.drop_all()
    
    def test_subscription_crud(self):
        """Test subscription CRUD operations"""
        # Create subscription
        response = self.app.post('/api/subscriptions', 
                              json={'target_url': 'https://example.com/webhook'})
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        subscription_id = data['subscription']['id']
        
        # Get subscription
        response = self.app.get(f'/api/subscriptions/{subscription_id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['subscription']['target_url'], 'https://example.com/webhook')
        
        # Update subscription
        response = self.app.put(f'/api/subscriptions/{subscription_id}',
                             json={'target_url': 'https://example.com/updated'})
        self.assertEqual(response.status_code, 200)
        
        # Verify update
        response = self.app.get(f'/api/subscriptions/{subscription_id}')
        data = json.loads(response.data)
        self.assertEqual(data['subscription']['target_url'], 'https://example.com/updated')
        
        # Delete subscription
        response = self.app.delete(f'/api/subscriptions/{subscription_id}')
        self.assertEqual(response.status_code, 200)
        
        # Verify deletion
        response = self.app.get(f'/api/subscriptions/{subscription_id}')
        self.assertEqual(response.status_code, 404)
    
    def test_webhook_ingestion(self):
        """Test webhook ingestion"""
        # Create a subscription first
        with app.app_context():
            subscription = Subscription(target_url='https://example.com/webhook')
            db.session.add(subscription)
            db.session.commit()
            subscription_id = subscription.id
        
        # Ingest a webhook
        response = self.app.post(f'/api/ingest/{subscription_id}',
                              json={'event': 'test', 'data': 'test_data'})
        self.assertEqual(response.status_code, 202)
        data = json.loads(response.data)
        self.assertIn('delivery_id', data)
        
        # Verify delivery was created
        with app.app_context():
            delivery = WebhookDelivery.query.get(uuid.UUID(data['delivery_id']))
            self.assertIsNotNone(delivery)
            self.assertEqual(delivery.subscription_id, subscription_id)
            self.assertEqual(delivery.payload, {'event': 'test', 'data': 'test_data'})
    
    @patch('tasks.requests.post')
    def test_webhook_delivery(self, mock_post):
        """Test webhook delivery process"""
        # Mock the request response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = 'Success'
        mock_post.return_value = mock_response
        
        # Create test data
        with app.app_context():
            # Create subscription
            subscription = Subscription(target_url='https://example.com/webhook')
            db.session.add(subscription)
            db.session.commit()
            
            # Create delivery
            delivery = WebhookDelivery(
                subscription_id=subscription.id,
                payload={'event': 'test', 'data': 'test_data'}
            )
            db.session.add(delivery)
            db.session.commit()
            
            # Attempt delivery
            result = attempt_delivery(delivery, subscription, 1)
            
            # Verify success
            self.assertEqual(result['status'], 'success')
            
            # Verify attempt was recorded
            attempt = DeliveryAttempt.query.filter_by(delivery_id=delivery.id).first()
            self.assertIsNotNone(attempt)
            self.assertEqual(attempt.status, 'success')
            self.assertEqual(attempt.status_code, 200)
    
    def test_event_type_filtering(self):
        """Test event type filtering"""
        # Create a subscription with event type filtering
        with app.app_context():
            subscription = Subscription(
                target_url='https://example.com/webhook',
                event_types=['order.created', 'user.updated']
            )
            db.session.add(subscription)
            db.session.commit()
            subscription_id = subscription.id
        
        # Send webhook with matching event type
        response = self.app.post(f'/api/ingest/{subscription_id}',
                              json={'event': 'test'},
                              headers={'X-Event-Type': 'order.created'})
        self.assertEqual(response.status_code, 202)
        
        # Send webhook with non-matching event type
        response = self.app.post(f'/api/ingest/{subscription_id}',
                              json={'event': 'test'},
                              headers={'X-Event-Type': 'order.deleted'})
        self.assertEqual(response.status_code, 202)  # Still accepted but won't be processed
    
    def test_log_cleanup(self):
        """Test log cleanup functionality"""
        # Create test data with old and new logs
        with app.app_context():
            # Create subscription
            subscription = Subscription(target_url='https://example.com/webhook')
            db.session.add(subscription)
            db.session.commit()
            
            # Create old delivery (beyond retention period)
            old_delivery = WebhookDelivery(
                subscription_id=subscription.id,
                payload={'event': 'test_old'},
                created_at=datetime.utcnow() - timedelta(hours=73)  # 73 hours old (beyond 72h retention)
            )
            db.session.add(old_delivery)
            
            # Create new delivery (within retention period)
            new_delivery = WebhookDelivery(
                subscription_id=subscription.id,
                payload={'event': 'test_new'},
                created_at=datetime.utcnow() - timedelta(hours=24)  # 24 hours old
            )
            db.session.add(new_delivery)
            db.session.commit()
            
            old_delivery_id = str(old_delivery.id)
            new_delivery_id = str(new_delivery.id)
            
            # Run cleanup task
            result = cleanup_old_delivery_logs()
            
            # Verify old delivery was deleted
            self.assertIsNone(WebhookDelivery.query.get(old_delivery_id))
            
            # Verify new delivery was kept
            self.assertIsNotNone(WebhookDelivery.query.get(new_delivery_id))

if __name__ == '__main__':
    unittest.main()
