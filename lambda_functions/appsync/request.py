"""
AWS AppSync GraphQL Resolver - AI Streaming Initiator

This Lambda function serves as a GraphQL resolver for the 'startStream' mutation in AppSync.
It demonstrates key serverless patterns for building responsive real-time applications:

Key Concepts Demonstrated:
1. GraphQL Resolvers - Lambda functions that execute GraphQL operations
2. Message-Based Processing - Decoupled via SQS rather than direct Lambda invocation
3. Session Management - Unique session tracking for concurrent users
4. Immediate Response Pattern - Quick acknowledgment to maintain UX
5. Event-Driven Architecture - Triggering workflows through SQS events

GraphQL Schema Integration:
This resolver handles the startStream mutation:

type Mutation {
    startStream(prompt: String!): StreamResponse
}

type StreamResponse {
    sessionId: String!
    status: String!
    message: String
    timestamp: String!
}

Architecture Flow:
Client → AppSync startStream mutation → This Lambda → SQS Queue → Worker Lambda
    ↓
Immediate response to client with sessionId
    ↓
Client subscribes to onTokenReceived(sessionId) for real-time updates
    ↓
Worker Lambda streams AI responses via GraphQL mutations → AppSync subscriptions

Benefits of This Pattern:
- No API Gateway timeouts (immediate response)
- Real-time user feedback through subscriptions
- Horizontal scaling of AI processing workloads
- Loose coupling through message-based architecture
- Enhanced resilience with SQS retry capabilities
"""

import json
import boto3
import uuid
import datetime
import os


def lambda_handler(event, context):
    """
    AppSync GraphQL Resolver for Starting AI Stream Sessions

    This function initiates AI streaming by immediately returning a session ID to the client
    while sending the processing request to an SQS queue. This pattern ensures responsive
    user experience while enabling long-running AI operations in a decoupled architecture.

    AppSync Event Structure:
    {
        "arguments": {
            "prompt": "User's question or request"
        },
        "source": null,
        "request": {
            "headers": {...},
            "userAgent": "...",
            "requestId": "..."
        },
        "prev": null,
        "info": {
            "fieldName": "startStream",
            "parentTypeName": "Mutation"
        }
    }

    Environment Variables:
    - STREAMING_QUEUE_URL: URL of the SQS queue for processing requests

    Returns:
        dict: Immediate response with session ID for client to track streaming

    Real-time Flow:
    1. Client calls startStream mutation
    2. This function returns sessionId immediately while sending request to SQS
    3. Client subscribes to onTokenReceived(sessionId)
    4. Worker Lambda (triggered by SQS) publishes tokens via AppSync subscriptions
    5. Client receives real-time AI responses
    """

    print(f"🎬 STARTER: GraphQL startStream mutation received")
    print(f"📋 STARTER: Event details: {json.dumps(event, default=str, indent=2)}")

    # Extract GraphQL arguments from AppSync event
    # Arguments come from the client's mutation variables
    arguments = event.get("arguments", {})
    prompt = arguments.get("prompt", "Hello, how are you?")

    # Generate unique session ID for tracking this streaming session
    # This ID is used by clients to subscribe to their specific stream
    session_id = str(uuid.uuid4())

    # Get SQS queue URL from environment
    # This is configured during CDK deployment
    queue_url = os.environ["STREAMING_QUEUE_URL"]

    print(f"🚀 STARTER: Generated session ID: {session_id}")
    print(f"📝 STARTER: Prompt preview: '{prompt[:100]}...'")  # Truncate for privacy
    print(f"📨 STARTER: Sending message to SQS queue: {queue_url}")

    try:
        # Initialize SQS client
        sqs_client = boto3.client("sqs")

        # Send message to SQS queue
        # The worker Lambda will be triggered by this SQS message
        response = sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(
                {
                    "prompt": prompt,
                    "sessionId": session_id,
                    "requestId": context.aws_request_id,
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                }
            ),
            MessageAttributes={
                "Type": {"DataType": "String", "StringValue": "llm-streaming-request"}
            },
        )

        print(
            f"✅ STARTER: Message sent to SQS successfully with ID: {response['MessageId']}"
        )
        print(f"📊 STARTER: Session {session_id} ready for real-time streaming")

        # Return immediate response to client
        # Client uses sessionId to subscribe to onTokenReceived subscription
        return {
            "sessionId": session_id,
            "status": "streaming_started",
            "message": "AI streaming session initiated. Subscribe to receive real-time tokens.",
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }

    except Exception as e:
        # Handle any errors during SQS message sending
        error_msg = str(e)
        print(f"❌ STARTER: Failed to send message to SQS: {error_msg}")

        # Return error response to client
        # Client should handle this error state appropriately
        return {
            "sessionId": session_id,
            "status": "error",
            "error": f"Failed to initiate streaming: {error_msg}",
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }
