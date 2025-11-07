"""
WebSocket API Lambda Authorizer for AWS Cognito JWT Token Validation

This function demonstrates WebSocket API authentication patterns in AWS:

Key Concepts:
1. WebSocket Authorization Flow - Unlike HTTP APIs, WebSocket authorization happens
   only once during the initial connection handshake
2. Query Parameter Authentication - Since WebSockets can't modify headers after
   connection, tokens are passed as query parameters
3. IAM Policy Generation - Authorizers return IAM policies that determine access
4. Connection-level Security - Authorization grants access to the entire WebSocket session

Authentication Flow:
Client → wss://api-id.execute-api.region.amazonaws.com/stage?token=JWT_TOKEN
         ↓
      Authorizer validates JWT
         ↓
      Returns Allow/Deny policy
         ↓
   Connection established/rejected
"""

import json
import jwt
from jwt import PyJWKClient
import os


def lambda_handler(event, context):
    """
    WebSocket Lambda Authorizer Handler

    This function is invoked during the WebSocket $connect route to validate
    the client's JWT token before allowing the connection to proceed.

    Event Structure:
    {
        "type": "REQUEST",
        "methodArn": "arn:aws:execute-api:region:account:api-id/stage/GET/$connect",
        "resource": "/$connect",
        "path": "/$connect",
        "httpMethod": "GET",
        "headers": {...},
        "queryStringParameters": {
            "token": "..."
        },
        "requestContext": {...}
    }

    Returns:
    IAM policy document that allows or denies the WebSocket connection
    """
    try:
        # Extract JWT token from query string parameters
        # WebSocket clients connect with: wss://api-url/stage?token=JWT_TOKEN
        token = event.get("queryStringParameters", {}).get("token")
        if not token:
            print("No token provided in query parameters")
            return generate_policy("user", "Deny", event["methodArn"])

        # Construct Cognito JWKS URL for token verification
        # JWKS (JSON Web Key Set) contains the public keys used to verify JWT signatures
        user_pool_id = os.environ["USER_POOL_ID"]
        region = context.invoked_function_arn.split(":")[
            3
        ]  # Extract region from Lambda ARN
        jwks_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"

        # Verify JWT token using Cognito's public keys
        # This process validates:
        # 1. Token signature using public key from JWKS
        # 2. Token expiration (exp claim)
        # 3. Token issuer (iss claim)
        # 4. Token format and structure
        jwks_client = PyJWKClient(jwks_url)
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        decoded_token = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],  # Cognito uses RS256 algorithm
            options={"verify_aud": False},  # Skip audience verification for simplicity
            issuer=f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}",
        )

        # Token is valid - generate Allow policy using user's unique identifier
        # The principalId (user's 'sub' claim) will be available in subsequent Lambda invocations
        print(f"Authorization successful for user: {decoded_token['sub']}")
        return generate_policy(decoded_token["sub"], "Allow", event["methodArn"])

    except jwt.ExpiredSignatureError:
        print("Authorization failed: Token has expired")
        return generate_policy("user", "Deny", event["methodArn"])
    except jwt.InvalidTokenError as e:
        print(f"Authorization failed: Invalid token - {str(e)}")
        return generate_policy("user", "Deny", event["methodArn"])
    except Exception as e:
        print(f"Authorization failed: {str(e)}")
        return generate_policy("user", "Deny", event["methodArn"])


def generate_policy(principal_id, effect, resource):
    """
    Generate IAM Policy Document for WebSocket API Authorization

    This function creates an IAM policy document that determines whether the
    WebSocket connection should be allowed or denied. The policy follows the
    standard AWS IAM policy format.

    Args:
        principal_id (str): Unique identifier for the user (typically Cognito 'sub' claim)
                           This ID will be available in subsequent Lambda invocations
        effect (str): "Allow" or "Deny" - determines access permission
        resource (str): The ARN of the API Gateway resource being accessed
                       Format: arn:aws:execute-api:region:account:api-id/stage/method/resource

    Returns:
        dict: IAM policy document in the format expected by API Gateway

    Policy Structure:
    {
        "principalId": "user-unique-id",           # Available in future Lambda calls
        "policyDocument": {                        # Standard IAM policy format
            "Version": "2012-10-17",
            "Statement": [{
                "Action": "execute-api:Invoke",    # Permission to invoke API Gateway
                "Effect": "Allow/Deny",            # Grant or deny access
                "Resource": "arn:aws:execute-api..." # Specific API resource
            }]
        }
    }

    WebSocket Authorization Behavior:
    - Allow: Client can connect and send messages to all routes
    - Deny: Connection is immediately rejected with 403 Forbidden
    - The policy applies to the entire WebSocket session lifecycle
    """
    return {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {"Action": "execute-api:Invoke", "Effect": effect, "Resource": resource}
            ],
        },
    }
