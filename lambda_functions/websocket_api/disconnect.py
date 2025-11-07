"""
WebSocket API $disconnect Route Handler

This function is automatically triggered when a WebSocket connection is closed,
either by the client or due to network issues. It handles cleanup tasks and
logging for the disconnected session.

WebSocket Disconnection Scenarios:
1. Client explicitly closes connection (client.close())
2. Network connectivity issues (timeout, connection reset)
3. Lambda function errors or timeouts
4. API Gateway enforced limits (idle timeout, etc.)
5. Client application crash or browser closure

Key Concepts:
- Automatic Invocation: This handler is called automatically by AWS
- Cleanup Opportunity: Perfect place for session cleanup and resource deallocation
- No Authorization Required: Disconnection doesn't need re-authorization
- Idempotent Operations: Handle multiple disconnect calls gracefully
- Connection State: Connection ID is still available for final operations
"""

import json


def lambda_handler(event, context):
    """
    Handle WebSocket Connection Termination

    This function is invoked when a WebSocket connection is closed for any reason.
    It's essential for:
    - Cleaning up connection state (DynamoDB records, cache entries)
    - Logging disconnection events for monitoring
    - Releasing allocated resources
    - Updating user presence/status
    - Finalizing any pending operations

    Event Structure:
    {
        "requestContext": {
            "connectionId": "L0SM9cOFvHcCIhw=",    # Connection being closed
            "eventType": "DISCONNECT",             # Event type
            "requestId": "c6af9ac6-7b61-11e6-...", # Request ID
            "stage": "prod",                       # API stage
            "identity": {
                "principalId": "user-sub-from-cognito"  # From original auth
            },
            "domainName": "1234567890.execute-api.us-west-2.amazonaws.com",
            "disconnectedAt": 1594129863999       # Disconnection timestamp
        },
        "headers": {...},
        "isBase64Encoded": false
    }

    Returns:
        dict: HTTP-style response (should always return 200)
    """

    # Extract connection information from the event
    connection_id = event["requestContext"]["connectionId"]
    stage = event["requestContext"]["stage"]
    domain_name = event["requestContext"]["domainName"]

    # Get user identity (preserved from original authorization)
    principal_id = event["requestContext"].get("identity", {}).get("principalId")

    # Log disconnection for monitoring and debugging
    print(f"WebSocket connection closed:")
    print(f"  Connection ID: {connection_id}")
    print(f"  User Principal: {principal_id}")
    print(f"  Endpoint: wss://{domain_name}/{stage}")
    print(f"  Disconnected at: {event['requestContext'].get('disconnectedAt')}")

    # Optional: Clean up connection state from DynamoDB
    # Remove the connection record that was created in $connect
    # This prevents stale connection records and enables accurate presence tracking
    #
    # Example DynamoDB cleanup:
    # try:
    #     dynamodb = boto3.resource('dynamodb')
    #     table = dynamodb.Table('WebSocketConnections')
    #     table.delete_item(Key={'connection_id': connection_id})
    #     print(f"Cleaned up connection record for {connection_id}")
    # except Exception as e:
    #     print(f"Error cleaning up connection record: {str(e)}")
    #     # Log error but don't fail the disconnect process

    # Optional: Update user presence status
    # Mark user as offline if this was their last active connection
    # This would require checking if the user has other active connections

    # Optional: Cancel any pending background operations
    # If there were any long-running processes associated with this connection,
    # this is the place to clean them up to prevent resource leaks

    # Return success response
    # Disconnect handlers should always return 200 to indicate successful cleanup
    # Even if cleanup operations fail, the connection will still be closed
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "Disconnected successfully",
                "connectionId": connection_id,
                "timestamp": event["requestContext"].get("disconnectedAt"),
            }
        ),
    }
