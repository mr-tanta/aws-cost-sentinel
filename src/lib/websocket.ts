import { EventEmitter } from 'events';

export interface WebSocketMessage {
  type: string;
  timestamp: string;
  [key: string]: any;
}

export interface WebSocketFilters {
  message_types?: string[];
  account_ids?: string[];
}

export interface ConnectionOptions {
  token: string;
  filters?: WebSocketFilters;
  reconnectAttempts?: number;
  reconnectDelay?: number;
}

export class WebSocketClient extends EventEmitter {
  private ws: WebSocket | null = null;
  private options: ConnectionOptions;
  private reconnectCount = 0;
  private pingInterval: NodeJS.Timeout | null = null;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private isConnecting = false;
  private shouldReconnect = true;

  constructor(options: ConnectionOptions) {
    super();
    this.options = {
      reconnectAttempts: 5,
      reconnectDelay: 5000,
      ...options,
    };
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN || this.isConnecting) {
      return;
    }

    this.isConnecting = true;
    const baseUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';
    const params = new URLSearchParams({
      token: this.options.token,
    });

    if (this.options.filters) {
      params.append('filters', JSON.stringify(this.options.filters));
    }

    const wsUrl = `${baseUrl}/api/v1/ws/connect?${params.toString()}`;

    try {
      this.ws = new WebSocket(wsUrl);
      this.setupEventListeners();
    } catch (error) {
      this.isConnecting = false;
      this.emit('error', error);
      this.scheduleReconnect();
    }
  }

  disconnect(): void {
    this.shouldReconnect = false;
    this.cleanup();

    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
    }
  }

  send(message: Record<string, any>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      this.emit('error', new Error('WebSocket is not connected'));
    }
  }

  updateFilters(filters: WebSocketFilters): void {
    this.options.filters = filters;
    this.send({
      type: 'subscribe',
      filters,
    });
  }

  private setupEventListeners(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      this.isConnecting = false;
      this.reconnectCount = 0;
      this.emit('connected');
      this.startPingInterval();
    };

    this.ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        this.handleMessage(message);
      } catch (error) {
        this.emit('error', new Error('Failed to parse WebSocket message'));
      }
    };

    this.ws.onclose = (event) => {
      this.isConnecting = false;
      this.cleanup();

      if (event.code !== 1000) { // Not a normal closure
        this.emit('disconnected', event);
        if (this.shouldReconnect) {
          this.scheduleReconnect();
        }
      } else {
        this.emit('disconnected', event);
      }
    };

    this.ws.onerror = (error) => {
      this.isConnecting = false;
      this.emit('error', error);
    };
  }

  private handleMessage(message: WebSocketMessage): void {
    // Handle different message types
    switch (message.type) {
      case 'ping':
        this.send({ type: 'pong', server_time: message.server_time });
        break;

      case 'pong':
        // Server responded to our ping
        break;

      case 'cost_update':
        this.emit('costUpdate', message);
        break;

      case 'waste_detected':
        this.emit('wasteDetected', message);
        break;

      case 'recommendation_ready':
        this.emit('recommendationReady', message);
        break;

      case 'job_status':
        this.emit('jobStatus', message);
        break;

      case 'account_status':
        this.emit('accountStatus', message);
        break;

      case 'error':
        this.emit('serverError', message);
        break;

      default:
        this.emit('message', message);
        break;
    }

    // Emit all messages with generic 'message' event
    this.emit('rawMessage', message);
  }

  private startPingInterval(): void {
    this.pingInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.send({ type: 'ping', client_time: new Date().toISOString() });
      }
    }, 30000); // Ping every 30 seconds
  }

  private cleanup(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }

    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
  }

  private scheduleReconnect(): void {
    if (!this.shouldReconnect ||
        (this.options.reconnectAttempts && this.reconnectCount >= this.options.reconnectAttempts)) {
      this.emit('reconnectFailed');
      return;
    }

    this.reconnectCount++;
    const delay = this.options.reconnectDelay! * Math.pow(1.5, this.reconnectCount - 1);

    this.emit('reconnecting', {
      attempt: this.reconnectCount,
      maxAttempts: this.options.reconnectAttempts,
      delay,
    });

    this.reconnectTimeout = setTimeout(() => {
      this.connect();
    }, delay);
  }

  // Getter methods
  get readyState(): number {
    return this.ws?.readyState ?? WebSocket.CLOSED;
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  get connectionState(): string {
    if (!this.ws) return 'disconnected';

    switch (this.ws.readyState) {
      case WebSocket.CONNECTING: return 'connecting';
      case WebSocket.OPEN: return 'connected';
      case WebSocket.CLOSING: return 'closing';
      case WebSocket.CLOSED: return 'disconnected';
      default: return 'unknown';
    }
  }
}

// React hook for WebSocket connection
export function useWebSocket(options: ConnectionOptions) {
  const [client] = React.useState(() => new WebSocketClient(options));
  const [connectionState, setConnectionState] = React.useState<string>('disconnected');
  const [lastMessage, setLastMessage] = React.useState<WebSocketMessage | null>(null);

  React.useEffect(() => {
    const handleConnected = () => setConnectionState('connected');
    const handleDisconnected = () => setConnectionState('disconnected');
    const handleReconnecting = () => setConnectionState('reconnecting');
    const handleMessage = (message: WebSocketMessage) => setLastMessage(message);

    client.on('connected', handleConnected);
    client.on('disconnected', handleDisconnected);
    client.on('reconnecting', handleReconnecting);
    client.on('rawMessage', handleMessage);

    client.connect();

    return () => {
      client.removeListener('connected', handleConnected);
      client.removeListener('disconnected', handleDisconnected);
      client.removeListener('reconnecting', handleReconnecting);
      client.removeListener('rawMessage', handleMessage);
      client.disconnect();
    };
  }, [client]);

  const sendMessage = React.useCallback((message: Record<string, any>) => {
    client.send(message);
  }, [client]);

  const updateFilters = React.useCallback((filters: WebSocketFilters) => {
    client.updateFilters(filters);
  }, [client]);

  return {
    client,
    connectionState,
    lastMessage,
    sendMessage,
    updateFilters,
    isConnected: connectionState === 'connected',
  };
}

// Notification types for type safety
export interface CostUpdateNotification extends WebSocketMessage {
  type: 'cost_update';
  account_id: string;
  data: {
    total_cost: number;
    previous_cost: number;
    change_percent: number;
    period: string;
  };
}

export interface WasteDetectedNotification extends WebSocketMessage {
  type: 'waste_detected';
  account_id: string;
  items_count: number;
  data: Array<{
    id: string;
    category: string;
    resource_id: string;
    estimated_savings: number;
  }>;
}

export interface RecommendationReadyNotification extends WebSocketMessage {
  type: 'recommendation_ready';
  account_id: string;
  recommendations_count: number;
  total_potential_savings: number;
  data: Array<{
    id: string;
    title: string;
    estimated_savings: number;
    confidence: number;
  }>;
}

export interface JobStatusNotification extends WebSocketMessage {
  type: 'job_status';
  job_id: string;
  status: string;
  progress: {
    percentage?: number;
    message?: string;
    current_step?: string;
    total_steps?: number;
  };
}

export interface AccountStatusNotification extends WebSocketMessage {
  type: 'account_status';
  account_id: string;
  status: string;
  health_data: {
    last_sync?: string;
    connection_status?: string;
    error_count?: number;
  };
}