# Webhook Delivery Service

A robust backend system that functions as a reliable webhook delivery service. This service ingests incoming webhooks, queues them, and attempts delivery to subscribed target URLs, handling failures with retries and providing visibility into delivery status.


## Features

- **Subscription Management**: Create, read, update, and delete webhook subscriptions
- **Webhook Ingestion**: Fast response API endpoint for receiving webhooks
- **Asynchronous Processing**: Background processing of webhook deliveries
- **Automatic Retries**: Exponential backoff for failed deliveries
- **Delivery Logging**: Comprehensive logging of all delivery attempts
- **Event Type Filtering**: Filter webhooks based on event types
- **Payload Signature Verification**: HMAC-SHA256 verification of payloads
- **Log Retention**: Automatic cleanup of old delivery logs
- **Status Monitoring**: Real-time status of webhook deliveries
- **Caching**: Redis-based caching for optimal performance

## Setup Instructions

### Prerequisites

- Docker and Docker Compose
- Git

### Local Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/Dhiren-Mhatre/webhook-delivery-service.git
   cd webhook-delivery-service
   ```

2. Create a `.env` file in the project root:
   ```bash
   cat > .env << 'EOF'
   # PostgreSQL configuration
   PGUSER=postgres
   PGPASSWORD=postgres
   PGDATABASE=webhookdb

   # Session secret
   SESSION_SECRET=your-secure-secret-key
   EOF
   ```

3. Create the entrypoint script:
   ```bash
   cat > entrypoint.sh << 'EOF'
   #!/bin/sh
   set -e

   # Wait for PostgreSQL to be ready
   echo "Waiting for PostgreSQL to be ready..."
   until PGPASSWORD=postgres psql -h db -U postgres -c '\q'; do
     >&2 echo "PostgreSQL is unavailable - sleeping"
     sleep 1
   done

   echo "PostgreSQL is up - executing command"
   exec "$@"
   EOF
   chmod +x entrypoint.sh
   ```

4. Build and start the containers:
   ```bash
   docker-compose build
   docker-compose up -d
   ```

5. Access the web interface:
   ```
   http://localhost:5000
   ```

### Troubleshooting

If you encounter any issues:

1. Check the logs:
   ```bash
   docker-compose logs -f
   ```

2. Ensure all containers are running:
   ```bash
   docker-compose ps
   ```

3. For database connection issues, verify PostgreSQL is accepting connections:
   ```bash
   docker-compose exec db psql -U postgres -c "SELECT 1"
   ```

4. For Redis issues:
   ```bash
   docker-compose exec redis redis-cli ping
   ```

5. To restart services:
   ```bash
   docker-compose restart web worker scheduler
   ```

## Architecture Choices

### Framework: Flask

I chose Flask for its lightweight nature and flexibility. For this service, which has specific, well-defined responsibilities, Flask provides the perfect balance of features without unnecessary overhead. It also integrates well with SQLAlchemy and Celery.

### Database: PostgreSQL

PostgreSQL was chosen for several reasons:
1. **Reliability**: Enterprise-grade reliability and ACID compliance
2. **JSON Support**: Native JSONB type for storing webhook payloads
3. **Array Support**: Native array type for storing event types
4. **Performance**: Strong performance even under high write loads
5. **Scalability**: Able to handle large volumes of delivery logs

### Asynchronous Tasks: Celery with Redis

Celery was chosen as the task queue system because:
1. **Reliability**: Robust handling of background tasks
2. **Retries**: Built-in support for retries with customizable backoff
3. **Scheduling**: Easy scheduling of periodic tasks like log cleanup
4. **Scalability**: Can be scaled horizontally by adding more workers

Redis serves as both the broker for Celery and as the caching system:
1. **Performance**: In-memory data store for fast operations
2. **Persistence**: Optional persistence for reliability
3. **Versatility**: Works well as both a cache and message broker
4. **Simplicity**: Simple to set up and maintain

### Containerization: Docker and Docker Compose

Docker containers provide:
1. **Isolation**: Consistent environment for all components
2. **Portability**: Works the same across different machines
3. **Scalability**: Easy to scale individual components
4. **Orchestration**: Docker Compose simplifies multi-container setup

## Database Schema and Indexing

### Schema

The application uses three main tables:

1. **Subscriptions**:
   ```sql
   CREATE TABLE subscriptions (
       id SERIAL PRIMARY KEY,
       name VARCHAR(100),
       target_url VARCHAR(255) NOT NULL,
       secret VARCHAR(255),
       event_types VARCHAR[] NULL,
       status VARCHAR(20) DEFAULT 'active',
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   ```

2. **WebhookDeliveries**:
   ```sql
   CREATE TABLE webhook_deliveries (
       id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
       subscription_id INTEGER REFERENCES subscriptions(id) NOT NULL,
       payload JSONB NOT NULL,
       event_type VARCHAR(100),
       status VARCHAR(20) DEFAULT 'pending',
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       completed_at TIMESTAMP
   );
   ```

3. **DeliveryAttempts**:
   ```sql
   CREATE TABLE delivery_attempts (
       id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
       delivery_id UUID REFERENCES webhook_deliveries(id) NOT NULL,
       attempt_number INTEGER NOT NULL,
       status VARCHAR(20) NOT NULL,
       status_code INTEGER,
       error_details TEXT,
       response_body TEXT,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   ```

### Indexing Strategy

The following indexes are created to optimize query performance:

1. **On webhook_deliveries**:
   - Index on subscription_id for quick lookups of deliveries by subscription
   - Index on created_at for efficient log retention queries
   - Index on status for filtering deliveries by status

2. **On delivery_attempts**:
   - Index on delivery_id for looking up attempts for a specific delivery
   - Composite index (delivery_id, attempt_number) for ordering attempts

These indexes help optimize:
- Webhook status lookups
- Recent delivery retrieval for dashboards
- Log cleanup operations
- Delivery attempt history retrieval

## API Endpoints

### Subscription Management

#### List all subscriptions
```bash
curl -X GET http://localhost:5000/api/subscriptions
```

#### Create a subscription
```bash
curl -X POST \
  http://localhost:5000/api/subscriptions \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Example Webhook",
    "target_url": "https://example.com/webhook",
    "secret": "my-secret-key",
    "event_types": ["order.created", "user.updated"],
    "status": "active"
  }'
```

#### Get a subscription
```bash
curl -X GET http://localhost:5000/api/subscriptions/1
```

#### Update a subscription
```bash
curl -X PUT \
  http://localhost:5000/api/subscriptions/1 \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Updated Webhook",
    "target_url": "https://example.com/new-webhook",
    "event_types": ["order.created"]
  }'
```

#### Delete a subscription
```bash
curl -X DELETE http://localhost:5000/api/subscriptions/1
```

### Webhook Ingestion

#### Send a webhook without event type
```bash
curl -X POST \
  http://localhost:5000/api/ingest/1 \
  -H 'Content-Type: application/json' \
  -d '{
    "event": "test",
    "data": "test_data"
  }'
```

#### Send a webhook with event type
```bash
curl -X POST \
  http://localhost:5000/api/ingest/1 \
  -H 'Content-Type: application/json' \
  -H 'X-Event-Type: order.created' \
  -d '{
    "order_id": "12345",
    "customer": "John Doe",
    "amount": 99.99
  }'
```

#### Send a webhook with signature
```bash
# Assuming "my-secret-key" is the secret for subscription with ID 1
# You'll need to generate the actual signature in your script
curl -X POST \
  http://localhost:5000/api/ingest/1 \
  -H 'Content-Type: application/json' \
  -H 'X-Hub-Signature-256: sha256=<calculated-signature>' \
  -d '{
    "event": "test",
    "data": "test_data"
  }'
```

### Delivery Status

#### Get webhook delivery status
```bash
curl -X GET http://localhost:5000/api/delivery/<delivery_id>
```

#### Get recent deliveries for a subscription
```bash
curl -X GET http://localhost:5000/api/subscriptions/1/deliveries
```

## Estimated Monthly Cost

The application is designed to run efficiently on free-tier cloud services. Below is an estimation for moderate traffic (5,000 webhooks per day with an average of 1.2 delivery attempts per webhook):

### AWS Free Tier
- **EC2 t2.micro** (750 hours/month free): $0
- **RDS PostgreSQL** (750 hours/month free, 20GB storage): $0 for first 12 months
- **ElastiCache (Redis)** (750 hours/month free): $0 for first 12 months

### Render Free Tier
- **Web Service** (750 hours/month free): $0
- **PostgreSQL** (Free tier with limitations): $0
- **Redis** (Not available in free tier, would need minimal plan): ~$7/month

### Monthly Data Calculation
- 5,000 webhooks/day × 30 days = 150,000 webhooks/month
- 150,000 webhooks × 1.2 attempts = 180,000 delivery attempts/month
- Average payload size: ~1KB
- Storage required for logs: ~500MB/month (with compression)

### Estimated Total Monthly Cost
- **AWS**: $0 for first 12 months, then ~$15-25/month
- **Heroku**: $0 with free tier limitations, ~$20-30/month for production usage
- **Render**: ~$7-15/month

The application is optimized to stay within free tier limits for development/demo purposes, with log rotation and cleanup to manage storage usage.

## Assumptions

1. **Webhook Payload Size**: The service assumes most webhook payloads will be under 100KB. Extremely large payloads might cause performance issues.

2. **Target Endpoint Reliability**: The service assumes target endpoints generally respond within the 10-second timeout window. Endpoints that consistently timeout might experience higher failure rates.

3. **Event Types**: The system supports a predefined set of event types that can be extended as needed.

4. **Security**: The service assumes HTTPS for production deployments and proper network security configurations.

5. **Scalability**: The current architecture can handle the specified load (5,000 webhooks/day) without modification, but would need adjustments for higher loads.

6. **Persistent Storage**: The service assumes persistence of webhook delivery information across service restarts.

7. **Error Handling**: The service assumes that transient errors (like network issues) might resolve on retry, while permanent errors (like invalid URLs) will fail consistently.

## Credits and Tools Used

### Libraries and Frameworks
- **Flask**: Web framework
- **SQLAlchemy**: ORM for database interactions
- **Celery**: Distributed task queue
- **Redis**: Message broker and caching
- **Psycopg2**: PostgreSQL adapter
- **Flask-SQLAlchemy**: Flask integration for SQLAlchemy
- **Flask-Caching**: Caching extension for Flask

### Development Tools
- **Docker & Docker Compose**: Containerization
- **Git**: Version control
- **Visual Studio Code**: Code editor

### External Resources
- **PostgreSQL Documentation**: Database design reference
- **Celery Documentation**: Task queue implementation reference
- **Flask Documentation**: Web framework reference
- **Docker Documentation**: Containerization reference

---
