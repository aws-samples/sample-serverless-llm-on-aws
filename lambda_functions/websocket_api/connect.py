"""
WebSocket API $connect Route Handler

This function is triggered when a client successfully establishes a WebSocket connection
after passing through the Lambda authorizer. It handles connection setup, logging,
and any initialization tasks needed for the WebSocket session.

WebSocket Connection Lifecycle:
1. Client attempts connection with: wss://api-id.execute-api.region.amazonaws.com/stage?token=JWT_TOKEN
2. Lambda Authorizer validates the JWT token
3. If authorized, this $connect handler is invoked
4. Connection is established and ready for bidirectional messaging
5. Client can now send messages to custom routes (like "stream")
6. $disconnect handler is called when connection closes

Key Concepts:
- Connection ID: Unique identifier for this WebSocket connection
- Persistent Connection: Unlike HTTP, WebSocket connections remain open
- Bidirectional Communication: Both client and server can initiate messages
- Connection Context: Information about the connection is available throughout the session
"""

import json


def lambda_handler(event, context):
    """
    Handle WebSocket Connection Establishment

    This function is invoked after successful authorization when a client
    connects to the WebSocket API. It's the perfect place for:
    - Connection logging and monitoring
    - User session initialization
    - Connection metadata storage (DynamoDB, etc.)
    - Sending welcome messages
    - Rate limiting setup

    Event Structure:
    {
        "requestContext": {
            "connectionId": "L0SM9cOFvHcCIhw=",    # Unique connection identifier
            "eventType": "CONNECT",                # Event type
            "requestId": "c6af9ac6-7b61-11e6-...", # Request ID
            "stage": "prod",                       # API stage
            "identity": {
                "principalId": "user-sub-from-cognito"  # From authorizer
            },
            "domainName": "1234567890.execute-api.us-west-2.amazonaws.com",
            "connectedAt": 1594129863110          # Connection timestamp
        },
        "headers": {...},
        "isBase64Encoded": false
    }

    Returns:
        dict: HTTP-style response (200 = success, connection proceeds)
    """

    # Extract connection information from the event
    connection_id = event["requestContext"]["connectionId"]
    stage = event["requestContext"]["stage"]
    domain_name = event["requestContext"]["domainName"]

    # Get user identity from the authorizer (if authorization was successful)
    # This comes from the principalId returned by the Lambda authorizer
    principal_id = event["requestContext"].get("identity", {}).get("principalId")

    # Log successful connection for monitoring and debugging
    print(f"WebSocket connection established:")
    print(f"  Connection ID: {connection_id}")
    print(f"  User Principal: {principal_id}")
    print(f"  Endpoint: wss://{domain_name}/{stage}")
    print(f"  Connected at: {event['requestContext'].get('connectedAt')}")

    # Optional: Store connection information in DynamoDB for session management
    # This would enable features like:
    # - User presence tracking
    # - Connection cleanup
    # - Message routing to specific users
    # - Rate limiting per user
    #
    # Example DynamoDB storage:
    # dynamodb = boto3.resource('dynamodb')
    # table = dynamodb.Table('WebSocketConnections')
    # table.put_item(Item={
    #     'connection_id': connection_id,
    #     'user_id': principal_id,
    #     'connected_at': event['requestContext']['connectedAt'],
    #     'ttl': int(time.time()) + 86400  # 24 hour TTL
    # })

    # Return success response to complete the connection
    # Any non-200 status code will cause the connection to be rejected
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "Connected successfully",
                "connectionId": connection_id,
                "timestamp": event["requestContext"].get("connectedAt"),
            }
        ),
    }
