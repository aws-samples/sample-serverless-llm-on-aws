export interface AppSyncConfig {
  region: string;
  userPoolId: string;
  userPoolClientId: string;
  apiUrl: string;
}

export interface WebSocketConfig {
  region: string;
  userPoolId: string;
  userPoolClientId: string;
  websocketUrl: string;
}

export interface LambdaUrlConfig {
  region: string;
  userPoolId: string;
  userPoolClientId: string;
  functionUrl: string;
}

export interface WebSocketMessage {
  type: "start" | "stream" | "complete" | "error" | "token";
  sessionId?: string;
  prompt?: string;
  error?: string;
  token?: string;
  timestamp: string;
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
  type: "info" | "success" | "error" | "warning";
}

export interface StreamToken {
  token: string;
  timestamp: Date;
  isComplete: boolean;
}

export interface StreamingSession {
  sessionId: string;
  prompt: string;
  status: "streaming" | "completed" | "error";
  tokens: StreamToken[];
  startTime: Date;
  endTime?: Date;
} 