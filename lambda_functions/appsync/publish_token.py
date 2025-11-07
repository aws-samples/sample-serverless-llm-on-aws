"""
AWS AppSync GraphQL Resolver - Token Publication Handler

This Lambda function serves as a GraphQL resolver for the 'publishToken' mutation in AppSync.
It demonstrates the core mechanism of real-time subscriptions in GraphQL applications:

Key Concepts Demonstrated:
1. GraphQL Subscriptions - Real-time data publishing to connected clients
2. Mutation Resolvers - Processing and transforming data before publication
3. Session-based Broadcasting - Targeting specific users/sessions
4. Data Persistence - Optional storage for conversation history
5. Real-time Pub/Sub - AppSync's built-in subscription infrastructure

GraphQL Schema Integration:
This resolver handles the publishToken mutation and triggers subscriptions:

type Mutation {
    publishToken(sessionId: String!, token: String!, isComplete: Boolean!): TokenData
}

type Subscription {
    onTokenReceived(sessionId: String!): TokenData
        @aws_subscribe(mutations: ["publishToken"])
}

type TokenData {
    sessionId: String!
    token: String!
    isComplete: Boolean!
    timestamp: String!
}

AppSync Subscription Flow:
Worker Lambda → publishToken mutation → This resolver → AppSync subscriptions → Clients
    ↓
1. Worker Lambda calls GraphQL mutation with token data
2. This resolver processes and validates the token
3. AppSync automatically publishes to onTokenReceived subscribers
4. Connected clients receive real-time updates

Benefits of This Pattern:
- Real-time updates without polling
- Automatic connection management by AppSync
- Session-based filtering (only relevant clients get updates)
- Optional data persistence for conversation history
- Built-in scaling and connection handling
"""

import json
import datetime
import boto3
import os


def lambda_handler(event, context):
    """
    AppSync GraphQL Resolver for Publishing AI Tokens to Subscriptions

    This function is invoked by AppSync when the publishToken mutation is executed
    (typically called by the worker Lambda). It processes token data and triggers
    real-time subscriptions to connected clients.

    AppSync Event Structure:
    {
        "arguments": {
            "sessionId": "unique-session-identifier",
            "token": "AI-generated text chunk",
            "isComplete": false
        },
        "source": null,
        "request": {
            "headers": {...},
            "requestId": "..."
        },
        "info": {
            "fieldName": "publishToken",
            "parentTypeName": "Mutation"
        }
    }

    Returns:
        dict: Token data that AppSync publishes to onTokenReceived subscribers

    Subscription Targeting:
    - Only clients subscribed to onTokenReceived(sessionId) receive updates
    - This enables multiple concurrent AI conversations
    - Each session is isolated from others

    Optional Features:
    - Token persistence in DynamoDB for conversation history
    - Token filtering/processing before publication
    - Rate limiting and validation
    - Custom metadata attachment
    """

    print(f"📡 PUBLISHER: publishToken mutation received")

    # Extract GraphQL arguments from AppSync event
    # These come from the worker Lambda's GraphQL mutation call
    arguments = event.get("arguments", {})
    session_id = arguments.get("sessionId", "")
    token = arguments.get("token", "")
    is_complete = arguments.get("isComplete", False)

    # Add timestamp for client-side ordering and debugging
    timestamp = datetime.datetime.utcnow().isoformat()

    # Log token publication for monitoring and debugging
    # In production, consider structured logging for better observability
    if is_complete:
        print(f"🏁 PUBLISHER: Stream completed for session {session_id}")
    else:
        # Truncate token for privacy and log size management
        token_preview = token[:50] + "..." if len(token) > 50 else token
        print(
            f"📤 PUBLISHER: Publishing token for session {session_id}: '{token_preview}'"
        )

    # Production Enhancement Opportunities:
    # You could add additional logic here for:
    #
    # 1. Token Validation:
    #    - Verify session exists and is active
    #    - Check token content for inappropriate content
    #    - Validate token sequence/ordering
    #
    # 2. Data Processing:
    #    - Apply content filters or transformations
    #    - Add metadata (user info, timestamps, etc.)
    #    - Format tokens for specific client requirements
    #
    # 3. Rate Limiting:
    #    - Prevent rapid-fire token publishing
    #    - Implement backpressure for high-volume streams
    #
    # 4. Authentication/Authorization:
    #    - Verify caller has permission to publish to this session
    #    - Check user subscription limits
    #
    # 5. Monitoring & Analytics:
    #    - Track token generation rates
    #    - Monitor session durations
    #    - Collect usage metrics

    # Prepare response data for AppSync subscription publication
    # This exact data structure will be sent to all onTokenReceived subscribers
    # for this specific sessionId
    result = {
        "sessionId": session_id,
        "token": token,
        "isComplete": is_complete,
        "timestamp": timestamp,
    }

    # Optional: Persist tokens in DynamoDB for conversation history
    # This enables features like conversation replay, analytics, and audit trails
    try:
        # Example DynamoDB storage implementation
        # Uncomment and configure if you want persistent conversation history
        #
        # dynamodb = boto3.resource('dynamodb')
        # table = dynamodb.Table('StreamingTokens')  # Create this table in CDK
        #
        # # Store with composite key for efficient querying
        # table.put_item(Item={
        #     'session_id': session_id,
        #     'sequence': int(timestamp.replace(':', '').replace('-', '').replace('.', '')),
        #     'token': token,
        #     'is_complete': is_complete,
        #     'timestamp': timestamp,
        #     'ttl': int(datetime.datetime.utcnow().timestamp()) + (7 * 24 * 60 * 60)  # 7 day TTL
        # })
        #
        # print(f"💾 PUBLISHER: Token stored in DynamoDB for session {session_id}")
        pass

    except Exception as e:
        # Log storage errors but don't fail the real-time publication
        # Real-time streaming is more important than persistence
        print(f"⚠️ PUBLISHER: Warning - Could not store token in DynamoDB: {e}")

    # Return token data to AppSync
    # AppSync automatically publishes this to all clients subscribed to
    # onTokenReceived(sessionId: session_id)
    print(f"✅ PUBLISHER: Token published successfully for session {session_id}")
    return result
