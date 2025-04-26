import uuid
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.ext.mutable import MutableList
from app import db

class Subscription(db.Model):
    __tablename__ = 'subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    target_url = db.Column(db.String(255), nullable=False)
    secret = db.Column(db.String(255), nullable=True)
    event_types = db.Column(MutableList.as_mutable(ARRAY(db.String)), nullable=True)
    status = db.Column(db.String(20), default='active')  # active, inactive
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    deliveries = db.relationship('WebhookDelivery', backref='subscription', lazy=True,
                                cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'target_url': self.target_url,
            'secret': '••••••' if self.secret else None,  # Hide actual secret
            'event_types': self.event_types,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
        
    @property
    def has_secret(self):
        """Check if the subscription has a secret configured"""
        return bool(self.secret and self.secret.strip())
        
    @property
    def delivery_stats(self):
        """Get delivery statistics for this subscription"""
        from sqlalchemy import func
        
        # Get total deliveries
        total_deliveries = db.session.query(func.count(WebhookDelivery.id))\
            .filter(WebhookDelivery.subscription_id == self.id).scalar() or 0
            
        # Get successful deliveries
        successful_deliveries = db.session.query(func.count(WebhookDelivery.id))\
            .filter(WebhookDelivery.subscription_id == self.id)\
            .filter(WebhookDelivery.status == 'delivered').scalar() or 0
            
        # Calculate success rate
        success_rate = (successful_deliveries / total_deliveries * 100) if total_deliveries > 0 else 0
        
        return {
            'total': total_deliveries,
            'successful': successful_deliveries,
            'success_rate': round(success_rate, 1)
        }

class WebhookDelivery(db.Model):
    __tablename__ = 'webhook_deliveries'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False)
    payload = db.Column(JSONB, nullable=False)
    event_type = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, processing, delivered, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    attempts = db.relationship('DeliveryAttempt', backref='delivery', lazy=True,
                              cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': str(self.id),
            'subscription_id': self.subscription_id,
            'event_type': self.event_type,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }

class DeliveryAttempt(db.Model):
    __tablename__ = 'delivery_attempts'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    delivery_id = db.Column(UUID(as_uuid=True), db.ForeignKey('webhook_deliveries.id'), nullable=False)
    attempt_number = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False)  # success, failed
    status_code = db.Column(db.Integer, nullable=True)
    error_details = db.Column(db.Text, nullable=True)
    response_body = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': str(self.id),
            'delivery_id': str(self.delivery_id),
            'attempt_number': self.attempt_number,
            'status': self.status,
            'status_code': self.status_code,
            'error_details': self.error_details,
            'created_at': self.created_at.isoformat()
        }
