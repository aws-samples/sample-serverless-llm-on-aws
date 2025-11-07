import React, { useState, useEffect, useCallback } from "react";
import { Amplify } from "aws-amplify";
import {
  signIn,
  signOut,
  getCurrentUser,
  fetchAuthSession,
} from "aws-amplify/auth";
import type { LambdaUrlConfig, ConnectionStatus, DebugLog } from "../types";
import { getEnvConfig } from "../lib/env";

const LambdaUrlClient: React.FC = () => {
  const envConfig = getEnvConfig();

  const [config, setConfig] = useState<LambdaUrlConfig>({
    region: envConfig.region,
    userPoolId: envConfig.userPoolId,
    userPoolClientId: envConfig.userPoolClientId,
    functionUrl: envConfig.lambdaFunctionUrl,
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
  const [authToken, setAuthToken] = useState<string | null>(null);

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
          setConnectionStatus({
            isConnected: true,
            isAuthenticated: true,
            isStreaming: false,
          });
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
              isConnected: true,
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
          isConnected: true,
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
              isConnected: true,
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
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      addDebugLog(`❌ Sign out error: ${errorMessage}`, "error");
    }
  };

  const startStreaming = async () => {
    if (!authToken) {
      addDebugLog("❌ Please authenticate first", "error");
      return;
    }
    try {
      setConnectionStatus((prev) => ({ ...prev, isStreaming: true }));
      setStreamingOutput("");
      setTokenCount(0);

      addDebugLog("🚀 Starting Lambda Function URL streaming...", "info");

      const response = await fetch(config.functionUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({ prompt }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      if (!response.body) {
        throw new Error("No response body available for streaming");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      addDebugLog("✅ Streaming connection established", "success");

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          addDebugLog("🏁 Streaming completed", "success");
          break;
        }

        const chunk = decoder.decode(value, { stream: true });
        setStreamingOutput((prev) => prev + chunk);
        setTokenCount((prev) => prev + 1);
        addDebugLog(`📥 Chunk received: ${chunk.substring(0, 50)}...`, "info");
      }

      setConnectionStatus((prev) => ({ ...prev, isStreaming: false }));
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      addDebugLog(`❌ Streaming error: ${errorMessage}`, "error");
      setConnectionStatus((prev) => ({
        ...prev,
        isStreaming: false,
        error: errorMessage,
      }));
    }
  };

  return (
    <div>
      <div className="demo-info">
        <h3>⚡ Lambda Function URL Streaming</h3>
        <p>
          Direct streaming from <strong>Lambda Function URLs</strong> using
          response streaming and chunked transfer encoding.
        </p>
        <ul>
          <li>
            ✅ <strong>Response Streaming</strong> - Native Lambda feature
          </li>
          <li>
            ✅ <strong>Chunked Transfer</strong> - HTTP streaming protocol
          </li>
          <li>
            ✅ <strong>Simple HTTP</strong> - No WebSocket required
          </li>
          <li>
            ✅ <strong>Direct connection</strong> - Minimal latency
          </li>
        </ul>
      </div>

      <div className="setup-section">
        <h2>⚙️ Lambda Function URL Configuration</h2>
        <div className="input-group">
          <label htmlFor="functionUrl">Lambda Function URL:</label>
          <input
            type="url"
            id="functionUrl"
            value={config.functionUrl}
            onChange={(e) =>
              setConfig((prev) => ({ ...prev, functionUrl: e.target.value }))
            }
            placeholder="https://xxxxxxxxxx.lambda-url.region.on.aws/"
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

      <div
        className={`status ${
          connectionStatus.error
            ? "error"
            : connectionStatus.isStreaming
            ? "streaming"
            : connectionStatus.isAuthenticated
            ? "connected"
            : "connecting"
        }`}
      >
        {connectionStatus.error
          ? `Error: ${connectionStatus.error}`
          : connectionStatus.isStreaming
          ? "Streaming in progress..."
          : connectionStatus.isAuthenticated
          ? "Authenticated and ready to stream"
          : "Please sign in to start streaming"}
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
            !connectionStatus.isAuthenticated || connectionStatus.isStreaming
          }
        >
          {connectionStatus.isStreaming ? (
            <>
              <span className="loading-spinner"></span> Streaming...
            </>
          ) : (
            "Start Lambda URL Streaming"
          )}
        </button>
      </div>

      <div className="output-section">
        <h3>📺 Live Streaming Response</h3>
        <div className="streaming-output">
          {streamingOutput || 'Click "Start Lambda URL Streaming" to begin...'}
        </div>
        <div className="token-counter">
          Chunks: {tokenCount} | Method: Lambda Function URL
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

export default LambdaUrlClient;
