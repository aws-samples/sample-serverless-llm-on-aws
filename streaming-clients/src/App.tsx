import React from "react";
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Link,
  useLocation,
} from "react-router-dom";
import AppSyncClient from "./components/AppSyncClient";
import LambdaUrlClient from "./components/LambdaUrlClient";
import WebSocketClient from "./components/WebSocketClient";
import type { StreamingMethod } from "./types";

const Navigation: React.FC = () => {
  const location = useLocation();

  const getMethodFromPath = (path: string): StreamingMethod => {
    if (path.includes("/lambda-url")) return "lambda-url";
    if (path.includes("/websocket")) return "websocket";
    return "appsync";
  };

  const currentMethod = getMethodFromPath(location.pathname);

  return (
    <div className="navigation">
      <Link
        to="/lambda-url"
        className={`nav-button ${
          currentMethod === "lambda-url" ? "active" : ""
        }`}
      >
        ⚡ Lambda Function URL
      </Link>
      <Link
        to="/websocket"
        className={`nav-button ${
          currentMethod === "websocket" ? "active" : ""
        }`}
      >
        🔌 WebSocket API
      </Link>

      <Link
        to="/appsync"
        className={`nav-button ${currentMethod === "appsync" ? "active" : ""}`}
      >
        🚀 AppSync GraphQL Subscriptions
      </Link>
    </div>
  );
};

const HomePage: React.FC = () => (
  <div className="demo-info">
    <h3>🚀 Serverless LLM Streaming Clients</h3>
    <p>
      Choose your preferred streaming method to test real-time LLM responses:
    </p>

    <div className="method-options">
      <Link to="/lambda-url" className="method-card">
        <h4>⚡ Lambda Function URL Streaming</h4>
        <p>
          Direct streaming from Lambda Function URLs using response streaming.
          Simple HTTP-based approach with chunked transfer encoding.
        </p>
      </Link>

      <Link to="/websocket" className="method-card">
        <h4>🔌 API Gateway WebSocket</h4>
        <p>
          Bi-directional communication using API Gateway WebSocket API. Perfect
          for interactive conversations and real-time messaging.
        </p>
      </Link>

      <Link to="/appsync" className="method-card">
        <h4>🚀 AppSync GraphQL Subscriptions</h4>
        <p>
          Real-time streaming using AWS AppSync with GraphQL subscriptions.
          Supports WebSocket connections with automatic reconnection and
          sub-100ms latency.
        </p>
      </Link>
    </div>

    <div className="alert info">
      <strong>🎯 Production-Ready Streaming Infrastructure</strong>
      <br />
      All three methods demonstrate real serverless LLM streaming with AWS
      Bedrock integration, Cognito authentication, and production-grade error
      handling.
    </div>
  </div>
);

function App() {
  return (
    <Router>
      <div className="container">
        <h1>🤖 AWS Serverless LLM Streaming Demo</h1>

        <Navigation />

        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/appsync" element={<AppSyncClient />} />
          <Route path="/lambda-url" element={<LambdaUrlClient />} />
          <Route path="/websocket" element={<WebSocketClient />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
