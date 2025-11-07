import React, { useState, useEffect, useRef, useCallback } from "react";
import { Amplify } from "aws-amplify";
import {
  generateClient,
  type Client,
  type GraphQLResult,
} from "aws-amplify/api";
import { signIn, signOut, getCurrentUser } from "aws-amplify/auth";
import type { AuthUser, SignInInput } from "aws-amplify/auth";
import type {
  AppSyncConfig,
  ConnectionStatus,
  DebugLog,
  StreamToken,
  StreamingSession,
} from "../types";
import { getEnvConfig } from "../lib/env";

// Define a type for the subscription data to avoid 'any'
interface SubscriptionData {
  onTokenReceived: {
    sessionId: string;
    token: string;
    isComplete: boolean;
    timestamp: string;
  };
}

const AppSyncClient: React.FC = () => {
  const envConfig = getEnvConfig();

  const [config, setConfig] = useState<AppSyncConfig>({
    region: envConfig.region,
    userPoolId: envConfig.userPoolId,
    userPoolClientId: envConfig.userPoolClientId,
    apiUrl: envConfig.appSyncApiUrl,
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
  const [currentSession, setCurrentSession] = useState<StreamingSession | null>(
    null
  );
  const [debugLogs, setDebugLogs] = useState<DebugLog[]>([]);
  const [streamingOutput, setStreamingOutput] = useState("");
  const [tokenCount, setTokenCount] = useState(0);

  const client = useRef<Client | null>(null);
  const subscription = useRef<{ unsubscribe: () => void } | null>(null);

  const checkCurrentUser = useCallback(async () => {
    try {
      const user: AuthUser = await getCurrentUser();
      if (user) {
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
    } catch {
      // No current user, which is fine
      addDebugLog("ℹ️ No existing user session found", "info");
    }
  }, []);

  // Initialize Amplify and check for existing session
  useEffect(() => {
    try {
      Amplify.configure({
        API: {
          GraphQL: {
            endpoint: config.apiUrl,
            region: config.region,
            defaultAuthMode: "userPool",
          },
        },
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

      // @ts-expect-error: Ignoring type complexity issue with generateClient
      client.current = generateClient();
      addDebugLog("AWS Amplify configured successfully", "success");

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
        const existingUser: AuthUser = await getCurrentUser();
        if (existingUser) {
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
      } catch {
        // No existing user, proceed with sign in
      }

      const signInInput: SignInInput = {
        username: credentials.email,
        password: credentials.password,
      };
      await signIn(signInInput);

      const user: AuthUser = await getCurrentUser();
      addDebugLog(`✅ Signed in as: ${user.username}`, "success");

      setConnectionStatus((prev) => ({
        ...prev,
        isAuthenticated: true,
        isConnected: true,
      }));
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error
          ? error.message
          : String(error) || "Sign in failed";
      addDebugLog(`❌ Sign in failed: ${errorMessage}`, "error");

      // If there's already a signed in user, try to handle it
      if (errorMessage.includes("already a signed in user")) {
        addDebugLog(
          "🔄 Detected existing user, attempting to use current session...",
          "info"
        );
        try {
          const user: AuthUser = await getCurrentUser();
          addDebugLog(
            `✅ Using existing session for: ${user.username}`,
            "success"
          );
          setConnectionStatus((prev) => ({
            ...prev,
            isAuthenticated: true,
            isConnected: true,
          }));
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
      addDebugLog("👋 Signed out successfully", "info");
      setConnectionStatus({
        isConnected: false,
        isAuthenticated: false,
        isStreaming: false,
      });
      setCurrentSession(null);
      setStreamingOutput("");
      setTokenCount(0);
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      addDebugLog(`❌ Sign out error: ${errorMessage}`, "error");
    }
  };

  const startStreaming = async () => {
    if (!client.current || !connectionStatus.isAuthenticated) {
      addDebugLog("❌ Not authenticated or client not ready", "error");
      return;
    }

    try {
      setConnectionStatus((prev) => ({ ...prev, isStreaming: true }));
      setStreamingOutput("");
      setTokenCount(0);

      addDebugLog("🚀 Starting AppSync streaming session...", "info");

      // GraphQL mutation to start streaming
      const START_STREAM = `
        mutation StartStream($prompt: String!) {
          startStream(prompt: $prompt) {
            sessionId
            status
            message
            timestamp
          }
        }
      `;

      const result = (await client.current.graphql({
        query: START_STREAM,
        variables: { prompt },
      })) as GraphQLResult<{ startStream: StreamingSession }>;

      const sessionData = result.data.startStream;

      const session: StreamingSession = {
        sessionId: sessionData.sessionId,
        prompt,
        status: "streaming",
        tokens: [],
        startTime: new Date(),
      };

      setCurrentSession(session);
      addDebugLog(`✅ Session started: ${sessionData.sessionId}`, "success");
      addDebugLog(`📋 Session details: ${JSON.stringify(sessionData)}`, "info");

      // Test the GraphQL endpoint with a simple query first
      try {
        addDebugLog("🧪 Testing GraphQL connection...", "info");
        const testQuery = `
          query TestConnection {
            __typename
          }
        `;
        await client.current.graphql({
          query: testQuery,
        });
        addDebugLog("✅ GraphQL connection test successful", "success");
      } catch (testError: unknown) {
        const errorMessage =
          testError instanceof Error ? testError.message : String(testError);
        console.error("❌ GraphQL connection test failed:", errorMessage);
        addDebugLog(`❌ GraphQL test failed: ${errorMessage}`, "error");
      }

      // Subscribe to token stream with sessionId filtering
      const TOKEN_SUBSCRIPTION = `
        subscription OnTokenReceived($sessionId: String!) {
          onTokenReceived(sessionId: $sessionId) {
            sessionId
            token
            isComplete
            timestamp
          }
        }
      `;

      addDebugLog("🔔 Setting up GraphQL subscription...", "info");

      try {
        addDebugLog("🔔 Setting up direct GraphQL subscription...", "info");

        const subscriptionObservable = client.current.graphql({
          query: TOKEN_SUBSCRIPTION,
          variables: { sessionId: sessionData.sessionId },
          // REMOVED authMode: "iam" to use default (userPool)
        }) as {
          subscribe: (callbacks: {
            next: (response: { data: SubscriptionData }) => void;
            error: (err: unknown) => void;
            complete: () => void;
          }) => { unsubscribe: () => void };
        };

        subscription.current = subscriptionObservable.subscribe({
          next: (response: { data: SubscriptionData }) => {
            const data = response.data;
            console.log("🔔 AppSync subscription data received:", data);
            addDebugLog("✅ Subscription event received!", "success");

            if (data?.onTokenReceived) {
              const tokenData = data.onTokenReceived;
              console.log("✅ Token data received:", tokenData);
              addDebugLog(`📥 Token received: ${tokenData.token}`, "info");
              handleTokenReceived(tokenData);
            } else {
              console.log("⚠️ Unexpected subscription data:", data);
              addDebugLog(
                `⚠️ Unexpected subscription data format: ${JSON.stringify(
                  data
                )}`,
                "warning"
              );
            }
          },
          error: (err: unknown) => {
            const error = err as { errors?: { message: string }[] };
            console.error("❌ AppSync subscription error:", error);
            const errorMessage =
              error?.errors?.[0]?.message || "Unknown subscription error";
            addDebugLog(`❌ Subscription error: ${errorMessage}`, "error");
            addDebugLog(`🔍 Error details: ${JSON.stringify(error)}`, "error");
            setConnectionStatus((prev) => ({ ...prev, isStreaming: false }));
          },
          complete: () => {
            addDebugLog("🏁 Subscription completed", "info");
            setConnectionStatus((prev) => ({ ...prev, isStreaming: false }));
          },
        });

        addDebugLog("✅ Direct subscription created successfully", "success");
      } catch (subscriptionError: unknown) {
        console.error("❌ Subscription setup error:", subscriptionError);
        const errorMessage =
          subscriptionError instanceof Error
            ? subscriptionError.message
            : String(subscriptionError) || "Failed to create subscription";
        addDebugLog(`❌ Subscription setup error: ${errorMessage}`, "error");
        setConnectionStatus((prev) => ({ ...prev, isStreaming: false }));
      }
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      addDebugLog(`❌ Streaming error: ${errorMessage}`, "error");
      setConnectionStatus((prev) => ({ ...prev, isStreaming: false }));
    }
  };

  const handleTokenReceived = (
    tokenData: SubscriptionData["onTokenReceived"]
  ) => {
    const token: StreamToken = {
      token: tokenData.token,
      timestamp: new Date(tokenData.timestamp),
      isComplete: tokenData.isComplete,
    };

    if (token.isComplete) {
      addDebugLog("🏁 Streaming completed", "success");
      setConnectionStatus((prev) => ({ ...prev, isStreaming: false }));
      setCurrentSession((prev) =>
        prev ? { ...prev, status: "completed", endTime: new Date() } : null
      );
    } else {
      setStreamingOutput((prev) => prev + token.token);
      setTokenCount((prev) => prev + 1);
      addDebugLog(
        `📥 Token received: ${token.token.substring(0, 50)}...`,
        "info"
      );
    }
  };

  const stopStreaming = () => {
    if (subscription.current) {
      subscription.current.unsubscribe();
      subscription.current = null;
      addDebugLog("🛑 Streaming stopped by user", "info");
    }
    setConnectionStatus((prev) => ({ ...prev, isStreaming: false }));
  };

  return (
    <div>
      <div className="demo-info">
        <h3>🚀 AppSync GraphQL Subscriptions</h3>
        <p>
          Real-time streaming using <strong>AWS Amplify</strong> with GraphQL
          subscriptions and WebSocket connections.
        </p>
        <ul>
          <li>
            ✅ <strong>AWS Amplify API GraphQL</strong> - Official SDK
          </li>
          <li>
            ✅ <strong>Real-time subscriptions</strong> - WebSocket based
          </li>
          <li>
            ✅ <strong>Cognito User Pool</strong> authentication
          </li>
          <li>
            ✅ <strong>Auto-reconnection</strong> and error handling
          </li>
        </ul>
      </div>

      <div className="setup-section">
        <h2>⚙️ AppSync Configuration</h2>
        <div className="input-group">
          <label htmlFor="apiUrl">AppSync API URL:</label>
          <input
            type="url"
            id="apiUrl"
            value={config.apiUrl}
            onChange={(e) =>
              setConfig((prev) => ({ ...prev, apiUrl: e.target.value }))
            }
            placeholder="https://xxxxxxxxx.appsync-api.region.amazonaws.com/graphql"
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
        <div className="input-row">
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
          ? "Connected and ready to stream"
          : "Please sign in to start streaming"}
      </div>

      <div className="input-group">
        <label htmlFor="prompt">Enter your prompt:</label>
        <textarea
          id="prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Ask me anything! For example: 'What is the meaning of life?'"
          disabled={
            !connectionStatus.isAuthenticated || connectionStatus.isStreaming
          }
        />
      </div>

      <div className="controls">
        <button
          onClick={startStreaming}
          disabled={
            !connectionStatus.isAuthenticated ||
            !prompt ||
            connectionStatus.isStreaming
          }
        >
          {connectionStatus.isStreaming ? (
            <>
              <span className="loading-spinner"></span> Streaming...
            </>
          ) : (
            "Start Real-time Streaming"
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
            "Please authenticate and start streaming to see real-time responses..."}
        </div>
        <div className="token-counter">
          Tokens: {tokenCount} | Session: {currentSession?.sessionId || "None"}
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

export default AppSyncClient;
