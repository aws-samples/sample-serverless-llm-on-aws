import React, { useState, useRef, useEffect, useCallback } from "react";
import { Amplify } from "aws-amplify";
import {
  signIn,
  signOut,
  getCurrentUser,
  fetchAuthSession,
} from "aws-amplify/auth";
import type {
  WebSocketConfig,
  ConnectionStatus,
  DebugLog,
  WebSocketMessage,
} from "../types";
import { getEnvConfig } from "../lib/env";

const WebSocketClient: React.FC = () => {
  const envConfig = getEnvConfig();

  const [config, setConfig] = useState<WebSocketConfig>({
    region: envConfig.region,
    userPoolId: envConfig.userPoolId,
    userPoolClientId: envConfig.userPoolClientId,
    websocketUrl: envConfig.websocketUrl,
  });

  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>({
    isConnected: false,
    isAuthenticated: false,
    isStreaming: false,
  });

  const [credentials, setCredentials] = useState({
    email: envConfig.defaultEmail,
    password: envConfig.defaultPassword,
  });

  const [prompt, setPrompt] = useState(
    "What is the most interesting recent development in AI?"
  );
  const [debugLogs, setDebugLogs] = useState<DebugLog[]>([]);
  const [streamingOutput, setStreamingOutput] = useState("");
  const [tokenCount, setTokenCount] = useState(0);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [authToken, setAuthToken] = useState<string | null>(null);

  const websocket = useRef<WebSocket | null>(null);

  const checkCurrentUser = useCallback(async () => {
    try {
      const user = await getCurrentUser();
      if (user) {
        const session = await fetchAuthSession();
        const idToken = session.tokens?.idToken?.toString();

        if (idToken) {
          setAuthToken(idToken);
          addDebugLog(
            `✅ Found existing session for: ${user.username}`,
            "success"
          );
          setConnectionStatus((prev) => ({
            ...prev,
            isAuthenticated: true,
          }));
        }
      }
    } catch {
      // No current user, which is fine
      addDebugLog("ℹ️ No existing user session found", "info");
    }
  }, []);

  // Initialize Amplify and check for existing session
  useEffect(() => {
    try {
      Amplify.configure({
        Auth: {
          Cognito: {
            userPoolId: config.userPoolId,
            userPoolClientId: config.userPoolClientId,
            loginWith: {
              email: true,
            },
          },
        },
      });

      addDebugLog("AWS Amplify configured for authentication", "success");

      // Check if user is already signed in
      checkCurrentUser();
    } catch (error) {
      addDebugLog(`Amplify configuration error: ${error}`, "error");
    }
  }, [config, checkCurrentUser]);

  const addDebugLog = (message: string, type: DebugLog["type"] = "info") => {
    const log: DebugLog = {
      timestamp: new Date(),
      message,
      type,
    };
    setDebugLogs((prev) => [...prev.slice(-49), log]);
  };

  const handleSignIn = async () => {
    try {
      setConnectionStatus((prev) => ({ ...prev, isAuthenticated: false }));
      addDebugLog("🔐 Starting Cognito authentication...", "info");

      // Check if user is already signed in
      try {
        const existingUser = await getCurrentUser();
        if (existingUser) {
          const session = await fetchAuthSession();
          const idToken = session.tokens?.idToken?.toString();

          if (idToken) {
            setAuthToken(idToken);
            addDebugLog(
              `ℹ️ User ${existingUser.username} is already signed in`,
              "info"
            );
            setConnectionStatus((prev) => ({
              ...prev,
              isAuthenticated: true,
            }));
            return;
          }
        }
      } catch {
        // No existing user, proceed with sign in
      }

      await signIn({
        username: credentials.email,
        password: credentials.password,
      });

      const user = await getCurrentUser();
      const session = await fetchAuthSession();
      const idToken = session.tokens?.idToken?.toString();

      if (idToken) {
        setAuthToken(idToken);
        addDebugLog(`✅ Signed in as: ${user.username}`, "success");
        setConnectionStatus((prev) => ({
          ...prev,
          isAuthenticated: true,
        }));
      } else {
        throw new Error("Failed to get ID token");
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      addDebugLog(`❌ Sign in failed: ${errorMessage}`, "error");

      // If there's already a signed in user, try to handle it
      if (errorMessage.includes("already a signed in user")) {
        addDebugLog(
          "🔄 Detected existing user, attempting to use current session...",
          "info"
        );
        try {
          const user = await getCurrentUser();
          const session = await fetchAuthSession();
          const idToken = session.tokens?.idToken?.toString();

          if (idToken) {
            setAuthToken(idToken);
            addDebugLog(
              `✅ Using existing session for: ${user.username}`,
              "success"
            );
            setConnectionStatus((prev) => ({
              ...prev,
              isAuthenticated: true,
            }));
          } else {
            throw new Error("Failed to get ID token from existing session");
          }
        } catch {
          addDebugLog(
            "❌ Failed to get current user. Please sign out and try again.",
            "error"
          );
          setConnectionStatus((prev) => ({
            ...prev,
            isAuthenticated: false,
            error: "Please sign out and try again",
          }));
        }
      } else {
        setConnectionStatus((prev) => ({
          ...prev,
          isAuthenticated: false,
          error: errorMessage,
        }));
      }
    }
  };

  const handleSignOut = async () => {
    try {
      await signOut();
      setAuthToken(null);
      addDebugLog("👋 Signed out successfully", "info");
      setConnectionStatus({
        isConnected: false,
        isAuthenticated: false,
        isStreaming: false,
      });
      setStreamingOutput("");
      setTokenCount(0);
      setCurrentSessionId(null);
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      addDebugLog(`❌ Sign out error: ${errorMessage}`, "error");
    }
  };

  const connectWebSocket = () => {
    if (websocket.current?.readyState === WebSocket.OPEN) {
      addDebugLog("⚠️ WebSocket already connected", "warning");
      return;
    }

    if (!authToken) {
      addDebugLog(
        "❌ Authentication token not found. Please sign in first.",
        "error"
      );
      setConnectionStatus((prev) => ({
        ...prev,
        error: "Please sign in first.",
      }));
      return;
    }

    try {
      addDebugLog("🔗 Connecting to WebSocket API...", "info");

      const urlWithToken = `${config.websocketUrl}?token=${authToken}`;
      addDebugLog(`Connecting to: ${config.websocketUrl}`, "info");

      websocket.current = new WebSocket(urlWithToken);

      websocket.current.onopen = () => {
        addDebugLog("✅ WebSocket connected successfully", "success");
        setConnectionStatus((prev) => ({
          ...prev,
          isConnected: true,
          error: undefined,
        }));
      };

      websocket.current.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          handleWebSocketMessage(message);
        } catch {
          addDebugLog(
            `❌ Failed to parse WebSocket message: ${event.data}`,
            "error"
          );
        }
      };

      websocket.current.onclose = (event) => {
        addDebugLog(
          `🔌 WebSocket connection closed: ${event.code} - ${event.reason}`,
          "warning"
        );
        setConnectionStatus((prev) => ({
          ...prev,
          isConnected: false,
          isStreaming: false,
        }));
      };

      websocket.current.onerror = (error) => {
        addDebugLog(`❌ WebSocket error: ${error}`, "error");
        setConnectionStatus((prev) => ({
          ...prev,
          isConnected: false,
          error: "WebSocket connection failed",
        }));
      };
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      addDebugLog(`❌ WebSocket connection error: ${errorMessage}`, "error");
      setConnectionStatus((prev) => ({
        ...prev,
        isConnected: false,
        error: errorMessage,
      }));
    }
  };

  const disconnectWebSocket = () => {
    if (websocket.current) {
      websocket.current.close();
      websocket.current = null;
      addDebugLog("👋 WebSocket disconnected", "info");
      setConnectionStatus({
        isConnected: false,
        isAuthenticated: false,
        isStreaming: false,
      });
      setCurrentSessionId(null);
    }
  };

  const handleWebSocketMessage = (message: WebSocketMessage) => {
    addDebugLog(`📥 WebSocket message: ${message.type}`, "info");

    switch (message.type) {
      case "start":
        if (message.sessionId) {
          setCurrentSessionId(message.sessionId);
          setConnectionStatus((prev) => ({ ...prev, isStreaming: true }));
          addDebugLog(
            `🚀 Streaming session started: ${message.sessionId}`,
            "success"
          );
        }
        break;

      case "token":
        if (message.token) {
          setStreamingOutput((prev) => prev + message.token);
          setTokenCount((prev) => prev + 1);
          addDebugLog(
            `📝 Token received: ${message.token.substring(0, 50)}...`,
            "info"
          );
        }
        break;

      case "complete":
        addDebugLog("🏁 Streaming completed", "success");
        setConnectionStatus((prev) => ({ ...prev, isStreaming: false }));
        break;

      case "error":
        addDebugLog(`❌ Streaming error: ${message.error}`, "error");
        setConnectionStatus((prev) => ({
          ...prev,
          isStreaming: false,
          error: message.error,
        }));
        break;

      default:
        addDebugLog(`⚠️ Unknown message type: ${message.type}`, "warning");
    }
  };

  const startStreaming = () => {
    if (!websocket.current || websocket.current.readyState !== WebSocket.OPEN) {
      addDebugLog("❌ WebSocket not connected", "error");
      return;
    }

    try {
      setStreamingOutput("");
      setTokenCount(0);

      // The backend API Gateway route is selected based on the "action" field.
      const startMessage = {
        action: "stream",
        prompt,
        timestamp: new Date().toISOString(),
      };

      websocket.current.send(JSON.stringify(startMessage));
      addDebugLog("📤 Start streaming message sent", "info");
      setConnectionStatus((prev) => ({ ...prev, isStreaming: true }));
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      addDebugLog(`❌ Failed to start streaming: ${errorMessage}`, "error");
    }
  };

  const stopStreaming = () => {
    if (websocket.current && currentSessionId) {
      const stopMessage: WebSocketMessage = {
        type: "complete",
        sessionId: currentSessionId,
        timestamp: new Date().toISOString(),
      };

      websocket.current.send(JSON.stringify(stopMessage));
      addDebugLog("🛑 Stop streaming message sent", "info");
      setConnectionStatus((prev) => ({ ...prev, isStreaming: false }));
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (websocket.current) {
        websocket.current.close();
      }
    };
  }, []);

  return (
    <div>
      <div className="demo-info">
        <h3>🔌 API Gateway WebSocket</h3>
        <p>
          Bi-directional communication using{" "}
          <strong>API Gateway WebSocket API</strong> for interactive real-time
          messaging.
        </p>
        <ul>
          <li>
            ✅ <strong>WebSocket Protocol</strong> - Full-duplex communication
          </li>
          <li>
            ✅ <strong>API Gateway managed</strong> - Serverless WebSocket
          </li>
          <li>
            ✅ <strong>Real-time messaging</strong> - Instant bi-directional
          </li>
          <li>
            ✅ <strong>Connection management</strong> - Automatic scaling
          </li>
        </ul>
      </div>

      <div className="setup-section">
        <h2>⚙️ WebSocket API Configuration</h2>
        <div className="input-group">
          <label htmlFor="websocketUrl">WebSocket API URL:</label>
          <input
            type="url"
            id="websocketUrl"
            value={config.websocketUrl}
            onChange={(e) =>
              setConfig((prev) => ({ ...prev, websocketUrl: e.target.value }))
            }
            placeholder="wss://xxxxxxxxxx.execute-api.region.amazonaws.com/production"
          />
        </div>
        <div className="input-row">
          <div className="input-group">
            <label htmlFor="userPoolId">User Pool ID:</label>
            <input
              type="text"
              id="userPoolId"
              value={config.userPoolId}
              onChange={(e) =>
                setConfig((prev) => ({ ...prev, userPoolId: e.target.value }))
              }
              placeholder="us-east-1_xxxxxxxxx"
            />
          </div>
          <div className="input-group">
            <label htmlFor="userPoolClientId">User Pool Client ID:</label>
            <input
              type="text"
              id="userPoolClientId"
              value={config.userPoolClientId}
              onChange={(e) =>
                setConfig((prev) => ({
                  ...prev,
                  userPoolClientId: e.target.value,
                }))
              }
              placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxx"
            />
          </div>
        </div>
        <div className="input-group">
          <label htmlFor="region">AWS Region:</label>
          <input
            type="text"
            id="region"
            value={config.region}
            onChange={(e) =>
              setConfig((prev) => ({ ...prev, region: e.target.value }))
            }
            placeholder="us-east-1"
          />
        </div>
      </div>

      <div className="auth-section">
        <h2>🔐 Authentication</h2>
        <div className="input-row">
          <div className="input-group">
            <label htmlFor="email">Email:</label>
            <input
              type="email"
              id="email"
              value={credentials.email}
              onChange={(e) =>
                setCredentials((prev) => ({ ...prev, email: e.target.value }))
              }
              placeholder="your.email@example.com"
            />
          </div>
          <div className="input-group">
            <label htmlFor="password">Password:</label>
            <input
              type="password"
              id="password"
              value={credentials.password}
              onChange={(e) =>
                setCredentials((prev) => ({
                  ...prev,
                  password: e.target.value,
                }))
              }
              placeholder="Your password"
            />
          </div>
        </div>
        <div className="controls">
          <button
            onClick={handleSignIn}
            disabled={connectionStatus.isAuthenticated}
          >
            {connectionStatus.isAuthenticated ? "✅ Signed In" : "Sign In"}
          </button>
          <button
            onClick={handleSignOut}
            disabled={!connectionStatus.isAuthenticated}
          >
            Sign Out
          </button>
        </div>
      </div>

      <div className="controls">
        <button
          onClick={connectWebSocket}
          disabled={connectionStatus.isConnected}
        >
          {connectionStatus.isConnected ? "✅ Connected" : "Connect WebSocket"}
        </button>
        <button
          onClick={disconnectWebSocket}
          disabled={!connectionStatus.isConnected}
        >
          Disconnect
        </button>
      </div>

      <div
        className={`status ${
          connectionStatus.error
            ? "error"
            : connectionStatus.isStreaming
            ? "streaming"
            : connectionStatus.isConnected
            ? "connected"
            : "connecting"
        }`}
      >
        {connectionStatus.error
          ? `Error: ${connectionStatus.error}`
          : connectionStatus.isStreaming
          ? "Streaming in progress..."
          : connectionStatus.isConnected
          ? "Connected and ready to stream"
          : 'Click "Connect WebSocket" to establish connection'}
      </div>

      <div className="input-group">
        <label htmlFor="prompt">Enter your prompt:</label>
        <textarea
          id="prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Ask me anything! For example: 'Explain quantum computing in simple terms'"
        />
      </div>

      <div className="controls">
        <button
          onClick={startStreaming}
          disabled={
            !connectionStatus.isConnected || connectionStatus.isStreaming
          }
        >
          {connectionStatus.isStreaming ? (
            <>
              <span className="loading-spinner"></span> Streaming...
            </>
          ) : (
            "Start WebSocket Streaming"
          )}
        </button>
        <button
          onClick={stopStreaming}
          disabled={!connectionStatus.isStreaming}
        >
          Stop Streaming
        </button>
      </div>

      <div className="output-section">
        <h3>📺 Live Streaming Response</h3>
        <div className="streaming-output">
          {streamingOutput ||
            "Connect to WebSocket and start streaming to see real-time responses..."}
        </div>
        <div className="token-counter">
          Tokens: {tokenCount} | Session: {currentSessionId || "None"}
        </div>
      </div>

      <div className="debug-log">
        {debugLogs.map((log, index) => (
          <div key={index}>
            <span className="timestamp">[{log.timestamp.toISOString()}]</span>
            <span className={log.type}> {log.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default WebSocketClient;
