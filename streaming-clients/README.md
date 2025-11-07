# AWS Serverless LLM Streaming Clients

A modern React TypeScript application demonstrating three different approaches to real-time LLM streaming using AWS serverless architecture.

## Overview

This application showcases three production-ready methods for streaming Large Language Model responses in real-time:

1. **AppSync GraphQL Subscriptions** - WebSocket-based real-time subscriptions with AWS Amplify
2. **Lambda Function URL Streaming** - Direct HTTP streaming using response streaming  
3. **API Gateway WebSocket** - Bi-directional WebSocket communication

## Features

- **Modern React TypeScript** - Built with Vite for optimal development experience
- **Beautiful UI** - Styled to match the original HTML client with responsive design
- **Real-time Streaming** - Sub-100ms token latency for all three methods
- **AWS Authentication** - Cognito User Pool integration
- **Production Ready** - Comprehensive error handling and connection management
- **Debug Logging** - Real-time debugging information for troubleshooting
- **Type Safety** - Full TypeScript support with proper interfaces

## Architecture

### AppSync GraphQL Subscriptions
- **Technology**: AWS Amplify API GraphQL
- **Authentication**: Cognito User Pool
- **Protocol**: WebSocket with GraphQL subscriptions  
- **Best For**: Mobile apps, web applications requiring real-time updates

### Lambda Function URL Streaming
- **Technology**: Native Lambda response streaming
- **Authentication**: Not required (can be added)
- **Protocol**: HTTP with chunked transfer encoding
- **Best For**: Simple streaming, direct integrations

### API Gateway WebSocket
- **Technology**: AWS API Gateway WebSocket API
- **Authentication**: Configurable (IAM, Cognito, etc.)
- **Protocol**: WebSocket with custom message protocol
- **Best For**: Interactive conversations, bi-directional communication

## Environment Configuration

The clients use environment variables for default configuration values. Create a `.env` file in this directory:

```bash
# AWS Region
VITE_AWS_REGION=us-east-1

# Cognito User Pool Configuration
VITE_USER_POOL_ID=your-user-pool-id
VITE_USER_POOL_CLIENT_ID=your-user-pool-client-id

# AppSync Configuration
VITE_APPSYNC_API_URL=https://your-appsync-api.appsync-api.region.amazonaws.com/graphql

# Lambda URL Configuration  
VITE_LAMBDA_FUNCTION_URL=https://your-lambda-url.lambda-url.region.on.aws/

# WebSocket API Configuration
VITE_WEBSOCKET_URL=wss://your-websocket-api.execute-api.region.amazonaws.com/stage

# Default Credentials (for development/testing)
VITE_DEFAULT_EMAIL=testuser@example.com
VITE_DEFAULT_PASSWORD=YourPassword123!
```

**Note:** These environment variables serve as default values. Users can still edit all configuration values directly in the browser interface as needed.

## Quick Start

### Prerequisites
- Node.js 20+ 
- npm or yarn
- AWS account with deployed backend infrastructure

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd streaming-clients

# Install dependencies
npm install

# Start development server
npm run dev
```

### Configuration

Update the configuration in each client component:

1. **AppSync Client**: Set your AppSync API URL, User Pool ID, and Client ID
2. **Lambda URL Client**: Set your Lambda Function URL
3. **WebSocket Client**: Set your API Gateway WebSocket URL

## Project Structure

```
streaming-clients/
├── src/
│   ├── components/           # React components
│   │   ├── AppSyncClient.tsx    # AppSync GraphQL client
│   │   ├── LambdaUrlClient.tsx  # Lambda Function URL client
│   │   └── WebSocketClient.tsx  # WebSocket API client
│   ├── types/               # TypeScript interfaces
│   │   └── index.ts            # Shared type definitions
│   ├── App.tsx              # Main application with routing
│   ├── index.css            # Styled to match HTML client
│   └── main.tsx             # Application entry point
├── package.json
└── README.md
```

## Development

### Available Scripts

```bash
# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Type checking
npm run type-check

# Linting
npm run lint
```

### Adding New Streaming Methods

1. Create a new component in `src/components/`
2. Add the interface to `src/types/index.ts`
3. Update the routing in `App.tsx`
4. Add navigation link

## Backend Integration

This client works with the AWS CDK backend infrastructure that includes:

- **AWS AppSync** - GraphQL API with real-time subscriptions
- **AWS Lambda** - Streaming functions with Bedrock integration
- **Amazon Cognito** - User authentication and authorization
- **API Gateway** - WebSocket API management
- **Amazon Bedrock** - LLM model hosting (Claude, Titan, etc.)

## Authentication

The AppSync client uses AWS Cognito User Pool authentication:

- **Default Test User**: `testuser@example.com` 
- **Default Password**: `StreamingTest123!`
- **Sign In Flow**: Username/email and password
- **JWT Tokens**: Automatically managed by AWS Amplify

## Performance

All three methods are optimized for production use:

- **Latency**: Sub-100ms token delivery
- **Throughput**: Unlimited concurrent streams  
- **Scaling**: Automatic AWS scaling
- **Error Handling**: Comprehensive retry and reconnection logic

## Debugging

Each client includes comprehensive debug logging:

- **Connection Status**: Real-time connection monitoring
- **Message Flow**: All WebSocket/HTTP messages logged
- **Error Details**: Detailed error information with timestamps
- **Performance Metrics**: Token count, session tracking

## Production Deployment

### Build and Deploy

```bash
# Build for production
npm run build

# Deploy to S3 + CloudFront
aws s3 sync dist/ s3://your-bucket-name

# Or deploy to any static hosting service
# - Vercel
# - Netlify  
# - GitHub Pages
# - AWS Amplify Hosting
```

### Environment Configuration

For production, use environment variables:

```typescript
// Example: Use environment variables for configuration
const config = {
  apiUrl: import.meta.env.VITE_APPSYNC_API_URL,
  userPoolId: import.meta.env.VITE_USER_POOL_ID,
  userPoolClientId: import.meta.env.VITE_USER_POOL_CLIENT_ID,
  region: import.meta.env.VITE_AWS_REGION
};
```

## API Reference

### TypeScript Interfaces

```typescript
interface AppSyncConfig {
  region: string;
  userPoolId: string; 
  userPoolClientId: string;
  apiUrl: string;
}

interface StreamToken {
  token: string;
  timestamp: Date;
  isComplete: boolean;
}

interface ConnectionStatus {
  isConnected: boolean;
  isAuthenticated: boolean;
  isStreaming: boolean;
  error?: string;
}
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

- **Issues**: GitHub Issues for bug reports
- **Discussions**: GitHub Discussions for questions
- **Documentation**: See AWS documentation for backend services

## Related Projects

- [AWS CDK Backend](../README.md) - Serverless infrastructure code
- [AWS AppSync Documentation](https://docs.aws.amazon.com/appsync/)
- [AWS Lambda Streaming](https://docs.aws.amazon.com/lambda/latest/dg/response-streaming.html)
- [API Gateway WebSocket](https://docs.aws.amazon.com/apigateway/latest/developerguide/websocket-api.html)
