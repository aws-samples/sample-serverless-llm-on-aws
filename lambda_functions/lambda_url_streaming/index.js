/**
 * AWS Lambda Function for Streaming AI Responses using Bedrock
 * 
 * This function demonstrates several key AWS patterns:
 * 1. Lambda Response Streaming - enables real-time data streaming from Lambda
 * 2. Cognito JWT Authentication - validates user tokens
 * 3. Bedrock AI Integration - streams responses from Claude AI model
 * 4. CORS handling for web applications
 */

// AWS SDK v3 imports for Bedrock streaming functionality
const { BedrockRuntimeClient, InvokeModelWithResponseStreamCommand } = require('@aws-sdk/client-bedrock-runtime');

// AWS official JWT verification library for Cognito tokens
const { CognitoJwtVerifier } = require('aws-jwt-verify');

/**
 * Cognito JWT Verifier Configuration
 * 
 * The aws-jwt-verify library is AWS's official solution for verifying JWT tokens
 * from AWS services like Cognito. It automatically handles:
 * - JWKS (JSON Web Key Set) retrieval and caching
 * - Token signature verification
 * - Token expiration checking
 * - Issuer and audience validation
 * - Algorithm verification (RS256)
 * 
 * This is much more robust than manual JWT verification and is the recommended
 * approach for production applications.
 * 
 * COGNITO TOKEN TYPES EXPLAINED:
 * 
 * 1. ID Token: Contains user identity information (username, email, custom attributes)
 *    - Primary use: Identifying who the user is
 *    - Audience: Your application's client ID
 *    - Contains: User profile data, custom claims
 *    - When to use: When you need user identity information
 * 
 * 2. Access Token: Contains permissions and scopes for API access
 *    - Primary use: Authorizing API calls and resource access
 *    - Audience: Resource servers (APIs)
 *    - Contains: Scopes, permissions, token_use: "access"
 *    - When to use: When calling APIs that require authorization
 * 
 * For this AI streaming API, we're using ID tokens since we're primarily
 * identifying the user and the token audience is our client ID.
 */
const jwtVerifier = CognitoJwtVerifier.create({
  userPoolId: process.env.USER_POOL_ID,
  tokenUse: "id", // Changed to "id" since frontend sends ID tokens
  clientId: process.env.USER_POOL_CLIENT_ID,
});

/**
 * JWT Token Validation Function
 * 
 * Uses AWS's official jwt-verify library to validate Cognito ID tokens.
 * This library automatically handles all the complexity of JWT verification:
 * 
 * Automatic verification includes:
 * 1. Token signature verification using JWKS from Cognito
 * 2. Token expiration checking
 * 3. Issuer validation (Cognito User Pool)
 * 4. Audience validation (User Pool Client ID)
 * 5. Algorithm verification (RS256)
 * 6. Token format validation
 * 7. Token use validation (ensures it's an ID token)
 * 
 * The ID token payload includes user information like:
 * - sub: User's unique identifier
 * - email: User's email address
 * - cognito:username: Username in Cognito
 * - custom attributes: Any custom user data
 * 
 * @param {string} token - The JWT ID token to validate
 * @returns {Promise} - Resolves with decoded token payload or rejects with error
 */
async function validateToken(token) {
  try {
    // The verify method returns the decoded token payload if valid
    // For ID tokens, this includes user identity information
    const payload = await jwtVerifier.verify(token);
    
    // Optional: Log user information for debugging (remove in production)
    console.log(`Authenticated user: ${payload.sub} (${payload.email || payload['cognito:username']})`);
    
    return payload;
  } catch (error) {
    // aws-jwt-verify provides detailed error messages for debugging
    // Common errors: expired token, invalid signature, wrong token type
    throw new Error(`Token validation failed: ${error.message}`);
  }
}

/**
 * Main Lambda Handler with Response Streaming
 * 
 * This handler uses Lambda Response Streaming (awslambda.streamifyResponse) which allows
 * the function to stream data back to the client in real-time instead of waiting
 * for the complete response. This is essential for AI streaming applications.
 * 
 * Key concepts demonstrated:
 * - Response streaming for real-time data delivery
 * - CORS handling for web applications
 * - JWT authentication with Cognito
 * - Bedrock AI model streaming integration
 */
exports.handler = awslambda.streamifyResponse(async (event, responseStream, context) => {
  try {
    /**
     * CORS Preflight Request Handling
     * 
     * Browsers send OPTIONS requests before making actual requests to check
     * CORS permissions. While CDK configures CORS headers automatically,
     * we still need to handle the OPTIONS method explicitly in streaming functions.
     */
    if (event.requestContext.http.method === 'OPTIONS') {
      const response = {
        statusCode: 200
      };
      responseStream.write(JSON.stringify(response));
      responseStream.end();
      return;
    }

    /**
     * JWT Token Authentication
     * 
     * Extract and validate the Bearer token from the Authorization header.
     * This ensures only authenticated users can access the AI streaming endpoint.
     */
    const authHeader = event.headers.authorization || event.headers.Authorization;
    if (!authHeader) {
      const response = {
        statusCode: 401,
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ error: 'Authorization header required' })
      };
      responseStream.write(JSON.stringify(response));
      responseStream.end();
      return;
    }

    // Extract token from "Bearer <token>" format
    const token = authHeader.replace('Bearer ', '');
    
    // Validate the JWT ID token against Cognito User Pool
    // This returns user information that can be used for personalization,
    // logging, rate limiting, or user-specific AI model configurations
    const userInfo = await validateToken(token);
    
    // Example: You could use userInfo.sub for user-specific logging,
    // userInfo.email for personalized responses, or custom attributes
    // for user-specific AI model settings or rate limits

    /**
     * Extract Request Data
     * 
     * Parse the request body to get the user's prompt. Provide a default
     * prompt if none is specified for testing purposes.
     */
    const body = JSON.parse(event.body || '{}');
    const prompt = body.prompt || 'Hello, how are you?';

    /**
     * Bedrock Client Setup
     * 
     * Initialize the Bedrock Runtime client which handles communication
     * with AWS Bedrock AI models. The client uses the Lambda's IAM role
     * for authentication.
     */
    const bedrockClient = new BedrockRuntimeClient({ region: process.env.AWS_REGION });
    
    /**
     * Bedrock Streaming Command Configuration
     * 
     * Create a command to invoke Claude 3.5 Sonnet with response streaming.
     * Key parameters:
     * - modelId: Specifies the exact Claude model version
     * - body: Contains the Anthropic API format request
     * - anthropic_version: Required API version for Bedrock
     * - max_tokens: Limits the response length
     * - messages: Array of conversation messages (user/assistant format)
     */
    const command = new InvokeModelWithResponseStreamCommand({
      modelId: 'anthropic.claude-3-5-sonnet-20240620-v1:0',
      body: JSON.stringify({
        anthropic_version: 'bedrock-2023-05-31',
        max_tokens: 1000,
        messages: [{ role: 'user', content: prompt }]
      }),
      contentType: 'application/json',
      accept: 'application/json',
    });

    // Execute the Bedrock streaming command
    const response = await bedrockClient.send(command);
    
    /**
     * Configure Streaming Response Headers
     * 
     * Set up the HTTP response stream with appropriate headers for streaming:
     * - Content-Type: text/plain for streaming text data
     * - Cache-Control: no-cache prevents caching of streaming responses
     * - Connection: keep-alive maintains the connection for streaming
     */
    const metadata = {
      statusCode: 200,
      headers: {
        'Content-Type': 'text/plain',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive'
      }
    };
    
    // Transform the responseStream into an HTTP response stream with metadata
    responseStream = awslambda.HttpResponseStream.from(responseStream, metadata);
    console.log("response", response);

    /**
     * Process Bedrock Streaming Response
     * 
     * Iterate through the streaming response from Bedrock. The response comes
     * as chunks containing different types of data. We're specifically looking
     * for 'content_block_delta' chunks which contain the actual text being generated.
     * 
     * Stream Processing Flow:
     * 1. Receive chunk from Bedrock
     * 2. Check if chunk contains data (chunk.chunk exists)
     * 3. Decode the binary data to JSON
     * 4. Filter for text content chunks
     * 5. Stream text immediately to client
     */
    for await (const chunk of response.body) {
      console.log("chunk", chunk);
      if (chunk.chunk) {
        // Decode the binary chunk data to JSON
        const chunkData = JSON.parse(new TextDecoder().decode(chunk.chunk.bytes));
        console.log("chunkData", chunkData);
        
        // Only process content delta chunks (actual text generation)
        if (chunkData.type === 'content_block_delta') {
          console.log("chunkData.delta.text", chunkData.delta.text);
          // Stream the text chunk immediately to the client
          responseStream.write(chunkData.delta.text);
        }
      }
    }
    
    // Close the response stream to signal completion
    responseStream.end();
    
  } catch (error) {
    /**
     * Error Handling
     * 
     * Catch and handle any errors that occur during processing:
     * - JWT validation errors (invalid/expired tokens)
     * - Bedrock API errors (model unavailable, quota exceeded, etc.)
     * - Network/connectivity issues
     * - JSON parsing errors
     * 
     * Always return a proper HTTP error response and close the stream.
     */
    console.error('Error:', error);
    const errorResponse = {
      statusCode: 500,
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ error: error.message })
    };
    responseStream.write(JSON.stringify(errorResponse));
    responseStream.end();
  }
}); 