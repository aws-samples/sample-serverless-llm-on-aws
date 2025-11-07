// Environment configuration with fallbacks
// Users can create a .env file with VITE_ prefixed variables

export const getEnvConfig = () => ({
  // AWS Region
  region: import.meta.env.VITE_AWS_REGION || "us-east-1",
  
  // Cognito User Pool Configuration
  userPoolId: import.meta.env.VITE_USER_POOL_ID || "us-east-xxxxxxxx",
  userPoolClientId: import.meta.env.VITE_USER_POOL_CLIENT_ID || "xxxxxxxxxxxxxxx",
  
  // AppSync Configuration
  appSyncApiUrl: import.meta.env.VITE_APPSYNC_API_URL || "https://xxxxxxxx.appsync-api.us-east-1.amazonaws.com/graphql",
  
  // Lambda URL Configuration
  lambdaFunctionUrl: import.meta.env.VITE_LAMBDA_FUNCTION_URL || "https://xxxxxxxxxx.lambda-url.us-east-1.on.aws/",
  
  // WebSocket API Configuration
  websocketUrl: import.meta.env.VITE_WEBSOCKET_URL || "wss://xxxxxxxxxxx.execute-api.us-east-1.amazonaws.com/prod",
  
  // Default Credentials
  defaultEmail: import.meta.env.VITE_DEFAULT_EMAIL || "testuser@example.com",
  defaultPassword: import.meta.env.VITE_DEFAULT_PASSWORD || "StreamingTest123!",
});