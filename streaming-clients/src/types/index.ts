export interface AWSConfig {
  region: string;
  userPoolId: string;
  userPoolClientId: string;
}

export interface AppSyncConfig extends AWSConfig {
  apiUrl: string;
}

export interface LambdaUrlConfig extends AWSConfig {
  functionUrl: string;
}

export interface WebSocketConfig extends AWSConfig {
  websocketUrl: string;
}

export interface AuthTokens {
  idToken: string;
  accessToken: string;
  refreshToken: string;
}

export interface StreamingSession {
  sessionId: string;
  prompt: string;
  status: 'pending' | 'streaming' | 'completed' | 'error';
  tokens: StreamToken[];
  startTime: Date;
  endTime?: Date;
}

export interface StreamToken {
  token: string;
  timestamp: Date;
  isComplete: boolean;
}

export interface ConnectionStatus {
  isConnected: boolean;
  isAuthenticated: boolean;
  isStreaming: boolean;
  error?: string;
}

export interface DebugLog {
  timestamp: Date;
  message: string;
  type: 'info' | 'success' | 'error' | 'warning';
}

export interface StreamingClientProps {
  config: AppSyncConfig | LambdaUrlConfig | WebSocketConfig;
  onStatusChange: (status: ConnectionStatus) => void;
  onTokenReceived: (token: StreamToken) => void;
  onDebugLog: (log: DebugLog) => void;
}

// GraphQL Types for AppSync
export interface StartStreamMutation {
  startStream: {
    sessionId: string;
    status: string;
    message: string;
    timestamp: string;
  };
}

export interface TokenSubscription {
  onTokenReceived: {
    sessionId: string;
    token: string;
    isComplete: boolean;
    timestamp: string;
  };
}

// Lambda Function URL Response
export interface LambdaStreamResponse {
  sessionId: string;
  chunks: ReadableStreamDefaultReader;
}

// WebSocket Message Types
export interface WebSocketMessage {
  type: 'start' | 'token' | 'complete' | 'error';
  sessionId?: string;
  prompt?: string;
  token?: string;
  error?: string;
  timestamp: string;
}

export type StreamingMethod = 'appsync' | 'lambda-url' | 'websocket'; 