import express from 'express';
import cors from 'cors';
import { config } from 'dotenv';
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import axios, { AxiosInstance } from "axios";
import axiosRetry from 'axios-retry';
import { z } from "zod";

// Debug logging utility
class DebugLogger {
  private isDebug: boolean;

  constructor() {
    this.isDebug = process.env.DEBUG === 'true' || process.env.NODE_ENV === 'development';
  }

  get debugMode(): boolean {
    return this.isDebug;
  }

  log(message: string, data?: any) {
    if (this.isDebug) {
      const timestamp = new Date().toISOString();
      console.log(`[${timestamp}] 🔍 DEBUG: ${message}`);
      if (data) {
        console.log(`[${timestamp}] 📊 DATA:`, JSON.stringify(data, null, 2));
      }
    }
  }

  info(message: string, data?: any) {
    const timestamp = new Date().toISOString();
    console.log(`[${timestamp}] ℹ️  INFO: ${message}`);
    if (data && this.isDebug) {
      console.log(`[${timestamp}] 📊 DATA:`, JSON.stringify(data, null, 2));
    }
  }

  warn(message: string, data?: any) {
    const timestamp = new Date().toISOString();
    console.warn(`[${timestamp}] ⚠️  WARN: ${message}`);
    if (data && this.isDebug) {
      console.warn(`[${timestamp}] 📊 DATA:`, JSON.stringify(data, null, 2));
    }
  }

  error(message: string, error?: any) {
    const timestamp = new Date().toISOString();
    console.error(`[${timestamp}] ❌ ERROR: ${message}`);
    if (error && this.isDebug) {
      console.error(`[${timestamp}] 📊 ERROR:`, error);
    }
  }

  connection(clientIp: string, userAgent: string, method: string, url: string) {
    const timestamp = new Date().toISOString();
    console.log(`[${timestamp}] 🔗 CONNECTION: ${method} ${url} from ${clientIp}`);
    if (this.isDebug) {
      console.log(`[${timestamp}] 📱 USER-AGENT: ${userAgent}`);
    }
  }
}

// Load environment variables
config();

interface McpRequest {
  jsonrpc: "2.0";
  id: string | number;
  method: string;
  params?: any;
}

interface McpResponse {
  jsonrpc: "2.0";
  id: string | number;
  result?: any;
  error?: {
    code: number;
    message: string;
    data?: any;
  };
}

interface McpNotification {
  jsonrpc: "2.0";
  method: string;
  params?: any;
}

class ReadwiseMcpHttpServer {
  private app: express.Application;
  private mcpServer: McpServer;
  private axios: AxiosInstance;
  private port: number;
  private logger: DebugLogger;
  private serverInfo = {
    name: "Readwise MCP HTTP Server",
    version: "0.0.6"
  };

      constructor() {
    this.port = parseInt(process.env.PORT || '3000');
    this.app = express();
    this.logger = new DebugLogger();

    this.logger.info('Initializing Readwise MCP HTTP Server', {
      port: this.port,
      debug: this.logger.debugMode,
      nodeEnv: process.env.NODE_ENV
    });

    // Initialize MCP server
    this.mcpServer = new McpServer({
      name: "Readwise MCP HTTP Server",
      version: "0.0.6"
    });

    // Initialize axios client for Readwise API
    this.axios = axios.create({
      baseURL: process.env.BASE_URL ?? "https://readwise.io",
      timeout: 10000,
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Access-Token": process.env.ACCESS_TOKEN,
      },
    });

    // Add retry logic
    axiosRetry(
      this.axios,
      {
        retries: 3,
        retryDelay: () => 5000,
        retryCondition: (error) => {
          const responseStatus = error.response?.status;
          return !responseStatus || responseStatus >= 400
        }
      },
    );

    this.logger.info('Axios client configured with retry logic');

    this.setupMiddleware();
    this.setupMcpRoutes();
    this.registerTools();
    this.initializeReadwise();
  }

  private setupMiddleware() {
    this.logger.info('Setting up middleware');

    // CORS middleware
    this.app.use(cors());
    this.logger.log('CORS middleware enabled');

    // JSON parsing middleware
    this.app.use(express.json());
    this.logger.log('JSON parsing middleware enabled');

    // URL-encoded parsing middleware
    this.app.use(express.urlencoded({ extended: true }));
    this.logger.log('URL-encoded parsing middleware enabled');

    // Request logging middleware
    this.app.use((req, res, next) => {
      const clientIp = req.ip || req.connection.remoteAddress || 'unknown';
      const userAgent = req.get('User-Agent') || 'unknown';

      this.logger.connection(clientIp, userAgent, req.method, req.url);

      // Log request body in debug mode
      if (req.body && Object.keys(req.body).length > 0) {
        this.logger.log('Request body', req.body);
      }

      next();
    });

    this.logger.info('All middleware configured');
  }

      private registerTools() {
    this.logger.info('Registering MCP tools');

    // Register the search_readwise_highlights tool (same as the original module)
    this.mcpServer.tool(
      "search_readwise_highlights",
      {
        vector_search_term: z.string(),
        full_text_queries: z.array(
          z.object({
            field_name: z.enum([
              "document_author",
              "document_title",
              "highlight_note",
              "highlight_plaintext",
              "highlight_tags",
            ]),
            search_term: z.string(),
          })
        ),
      },
      async (payload) => {
        this.logger.log('Executing search_readwise_highlights tool', payload);
        const response = await this.axios.post("/api/mcp/highlights", payload);
        this.logger.log('Readwise API response received', { resultCount: response.data.results?.length || 0 });
        return { content: [{ type: "text", text: JSON.stringify(response.data.results) }] };
      }
    );

    this.logger.info('MCP tools registered successfully');
  }

  private setupMcpRoutes() {
    this.logger.info('Setting up MCP routes');

    // MCP HTTP endpoint - handles all MCP requests
    this.app.post('/mcp', async (req, res) => {
      try {
        this.logger.log('Processing MCP request', { method: req.method, url: req.url });

        const request: McpRequest = req.body;
        this.logger.log('MCP request received', request);

        if (!request.jsonrpc || request.jsonrpc !== "2.0") {
          this.logger.warn('Invalid JSON-RPC version', { jsonrpc: request.jsonrpc });
          return res.status(400).json({
            jsonrpc: "2.0",
            id: request.id || null,
            error: {
              code: -32600,
              message: "Invalid Request"
            }
          });
        }

        this.logger.log('Processing MCP method', { method: request.method, id: request.id });
        const response = await this.handleMcpRequest(request);
        this.logger.log('MCP response generated', response);

        res.json(response);
      } catch (error) {
        this.logger.error('MCP request error', error);
        res.status(500).json({
          jsonrpc: "2.0",
          id: req.body.id || null,
          error: {
            code: -32603,
            message: "Internal error"
          }
        });
      }
    });

        // MCP HTTP streaming endpoint
    this.app.post('/mcp/stream', async (req, res) => {
      try {
        this.logger.log('Processing MCP streaming request', { method: req.method, url: req.url });

        const request: McpRequest = req.body;
        this.logger.log('MCP streaming request received', request);

        if (!request.jsonrpc || request.jsonrpc !== "2.0") {
          this.logger.warn('Invalid JSON-RPC version in streaming request', { jsonrpc: request.jsonrpc });
          return res.status(400).json({
            jsonrpc: "2.0",
            id: request.id || null,
            error: {
              code: -32600,
              message: "Invalid Request"
            }
          });
        }

        this.logger.log('Setting up streaming response headers');
        // Set headers for streaming
        res.setHeader('Content-Type', 'application/json');
        res.setHeader('Transfer-Encoding', 'chunked');
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive');

        this.logger.log('Starting MCP streaming request handling');
        await this.handleMcpStreamRequest(request, res);
      } catch (error) {
        this.logger.error('MCP streaming error', error);
        res.status(500).json({
          jsonrpc: "2.0",
          id: req.body.id || null,
          error: {
            code: -32603,
            message: "Internal error"
          }
        });
      }
    });

    // Health check
    this.app.get('/health', (req, res) => {
      this.logger.log('Health check requested');
      res.json({
        status: 'ok',
        timestamp: new Date().toISOString(),
        server: this.serverInfo
      });
    });

    // MCP server info endpoint
    this.app.get('/mcp/info', (req, res) => {
      this.logger.log('MCP info requested');
      res.json({
        jsonrpc: "2.0",
        id: null,
        result: {
          name: this.serverInfo.name,
          version: this.serverInfo.version,
          capabilities: {
            tools: {
              listChanged: false
            }
          }
        }
      });
    });

    this.logger.info('All MCP routes configured');
  }

      private async handleMcpRequest(request: McpRequest): Promise<McpResponse> {
    this.logger.log('Handling MCP request', { method: request.method, id: request.id });

    switch (request.method) {
      case 'initialize':
        this.logger.log('Handling initialize method');
        return this.handleInitialize(request);

      case 'tools/list':
        this.logger.log('Handling tools/list method');
        return this.handleToolsList(request);

      case 'tools/call':
        this.logger.log('Handling tools/call method');
        return this.handleToolsCall(request);

      case 'notifications/list':
        this.logger.log('Handling notifications/list method');
        return this.handleNotificationsList(request);

      default:
        this.logger.warn('Unknown MCP method', { method: request.method });
        return {
          jsonrpc: "2.0",
          id: request.id,
          error: {
            code: -32601,
            message: "Method not found"
          }
        };
    }
  }

    private async handleMcpStreamRequest(request: McpRequest, res: express.Response) {
    this.logger.log('Handling MCP streaming request', { method: request.method, id: request.id });

    switch (request.method) {
      case 'tools/call':
        this.logger.log('Handling streaming tools/call method');
        await this.handleToolsCallStream(request, res);
        break;

      default:
        this.logger.log('Handling non-streaming method in stream endpoint');
        // For non-streaming methods, handle normally
        const response = await this.handleMcpRequest(request);
        res.write(JSON.stringify(response) + '\n');
        res.end();
    }
  }

    private async handleInitialize(request: McpRequest): Promise<McpResponse> {
    try {
      this.logger.log('Initializing Readwise MCP connection');
      await this.axios.post("/api/mcp/initialize");
      this.logger.log('Readwise MCP initialization successful');

      return {
        jsonrpc: "2.0",
        id: request.id,
        result: {
          protocolVersion: "2024-11-05",
          capabilities: {
            tools: {
              listChanged: false
            },
            resources: {
              subscribe: false,
              listChanged: false
            },
            prompts: {
              listChanged: false
            }
          },
          serverInfo: {
            name: this.serverInfo.name,
            version: this.serverInfo.version
          }
        }
      };
    } catch (error) {
      this.logger.error('Failed to initialize Readwise MCP', error);
      return {
        jsonrpc: "2.0",
        id: request.id,
        error: {
          code: -32603,
          message: "Failed to initialize Readwise MCP"
        }
      };
    }
  }

  private async handleToolsList(request: McpRequest): Promise<McpResponse> {
    this.logger.log('Returning available tools list');

    // Return the tools that we've registered (same as the original Readwise MCP module)
    return {
      jsonrpc: "2.0",
      id: request.id,
      result: {
        tools: [
          {
            name: "search_readwise_highlights",
            description: "Search through Readwise highlights using vector search and full-text queries",
            inputSchema: {
              type: "object",
              properties: {
                vector_search_term: {
                  type: "string",
                  description: "Semantic search term for vector search"
                },
                full_text_queries: {
                  type: "array",
                  items: {
                    type: "object",
                    properties: {
                      field_name: {
                        type: "string",
                        enum: [
                          "document_author",
                          "document_title",
                          "highlight_note",
                          "highlight_plaintext",
                          "highlight_tags"
                        ]
                      },
                      search_term: {
                        type: "string"
                      }
                    }
                  }
                }
              }
            }
          }
        ]
      }
    };
  }

      private async handleToolsCall(request: McpRequest): Promise<McpResponse> {
    try {
      const { name, arguments: args } = request.params;
      this.logger.log('Tool call requested', { toolName: name, arguments: args });

      if (name === 'search_readwise_highlights') {
        this.logger.log('Processing search_readwise_highlights tool call');

        // Use the same schema as the original Readwise MCP module
        const schema = z.object({
          vector_search_term: z.string(),
          full_text_queries: z.array(
            z.object({
              field_name: z.enum([
                "document_author",
                "document_title",
                "highlight_note",
                "highlight_plaintext",
                "highlight_tags",
              ]),
              search_term: z.string(),
            })
          ),
        });

        // Validate arguments and provide better error messages
        const validationResult = schema.safeParse(args);
        if (!validationResult.success) {
          this.logger.warn('Invalid tool arguments', {
            errors: validationResult.error.errors,
            received: args
          });
          const errorMessage = `Invalid arguments: ${validationResult.error.errors.map(e => e.message).join(', ')}`;
          return {
            jsonrpc: "2.0",
            id: request.id,
            result: {
              isError: true,
              content: [
                {
                  type: "text",
                  text: errorMessage
                }
              ],
              diagnostics: validationResult.error.errors
            }
          };
        }

        const payload = validationResult.data;
        this.logger.log('Validated tool arguments', payload);

        this.logger.log('Calling Readwise API', payload);
        const response = await this.axios.post("/api/mcp/highlights", payload);
        this.logger.log('Readwise API response received', { resultCount: response.data.results?.length || 0 });

        return {
          jsonrpc: "2.0",
          id: request.id,
          result: {
            content: [
              {
                type: "text",
                text: JSON.stringify(response.data.results)
              }
            ]
          }
        };
      }

      this.logger.warn('Unknown tool requested', { toolName: name });
      return {
        jsonrpc: "2.0",
        id: request.id,
        result: {
          isError: true,
          content: [
            {
              type: "text",
              text: `Tool "${name}" not found. Available tools: search_readwise_highlights`
            }
          ]
        }
      };
    } catch (error) {
      this.logger.error('Tool execution failed', error);
      const message = error instanceof Error ? error.message : 'Tool execution failed';
      const stack = error instanceof Error ? error.stack : undefined;
      return {
        jsonrpc: "2.0",
        id: request.id,
        result: {
          isError: true,
          content: [
            {
              type: "text",
              text: `Tool execution failed: ${message}`
            },
            ...(stack ? [{ type: "text", text: stack }] : [])
          ],
          ...(stack ? { diagnostics: stack } : {})
        }
      };
    }
  }

    private async handleToolsCallStream(request: McpRequest, res: express.Response) {
    try {
      const { name, arguments: args } = request.params;
      this.logger.log('Streaming tool call requested', { toolName: name, arguments: args });

      if (name === 'search_readwise_highlights') {
        this.logger.log('Processing streaming search_readwise_highlights tool call');

        const schema = z.object({
          vector_search_term: z.string().optional(),
          full_text_queries: z.array(
            z.object({
              field_name: z.enum([
                "document_author",
                "document_title",
                "highlight_note",
                "highlight_plaintext",
                "highlight_tags",
              ]),
              search_term: z.string(),
            })
          ).optional(),
        });

        const payload = schema.parse(args);
        this.logger.log('Validated streaming tool arguments', payload);

        if (!payload.vector_search_term && (!payload.full_text_queries || payload.full_text_queries.length === 0)) {
          this.logger.warn('Invalid streaming tool arguments - missing search terms');
          const errorResponse: McpResponse = {
            jsonrpc: "2.0",
            id: request.id,
            result: {
              isError: true,
              content: [
                {
                  type: "text",
                  text: "Either vector_search_term or full_text_queries must be provided"
                }
              ]
            }
          };
          res.write(JSON.stringify(errorResponse) + '\n');
          res.end();
          return;
        }

        this.logger.log('Sending initial streaming response');
        // Send initial response
        const initialResponse: McpResponse = {
          jsonrpc: "2.0",
          id: request.id,
          result: {
            content: [
              {
                type: "text",
                text: "Starting search..."
              }
            ]
          }
        };
        res.write(JSON.stringify(initialResponse) + '\n');

        this.logger.log('Calling Readwise API for streaming', payload);
        const response = await this.axios.post("/api/mcp/highlights", payload);
        const results = response.data.results;
        this.logger.log('Readwise API streaming response received', { resultCount: results?.length || 0 });

        // Stream results as separate MCP responses
        this.logger.log('Starting to stream results');
        for (let i = 0; i < results.length; i++) {
          const result = results[i];
          this.logger.log(`Streaming result ${i + 1}/${results.length}`);

          const streamResponse: McpResponse = {
            jsonrpc: "2.0",
            id: request.id,
            result: {
              content: [
                {
                  type: "text",
                  text: JSON.stringify(result)
                }
              ]
            }
          };
          res.write(JSON.stringify(streamResponse) + '\n');

          // Small delay for streaming effect
          await new Promise(resolve => setTimeout(resolve, 100));
        }

        this.logger.log('Sending streaming completion response');
        // Send completion response
        const completionResponse: McpResponse = {
          jsonrpc: "2.0",
          id: request.id,
          result: {
            content: [
              {
                type: "text",
                text: "Search completed."
              }
            ]
          }
        };
        res.write(JSON.stringify(completionResponse) + '\n');
        res.end();
        this.logger.log('Streaming completed');
      } else {
        this.logger.warn('Unknown streaming tool requested', { toolName: name });
        const errorResponse: McpResponse = {
          jsonrpc: "2.0",
          id: request.id,
          result: {
            isError: true,
            content: [
              {
                type: "text",
                text: `Tool "${name}" not found. Available tools: search_readwise_highlights`
              }
            ]
          }
        };
        res.write(JSON.stringify(errorResponse) + '\n');
        res.end();
      }
    } catch (error) {
      this.logger.error('Streaming tool execution failed', error);
      const message = error instanceof Error ? error.message : 'Tool execution failed';
      const stack = error instanceof Error ? error.stack : undefined;
      const errorResponse: McpResponse = {
        jsonrpc: "2.0",
        id: request.id,
        result: {
          isError: true,
          content: [
            {
              type: "text",
              text: `Tool execution failed: ${message}`
            },
            ...(stack ? [{ type: "text", text: stack }] : [])
          ],
          ...(stack ? { diagnostics: stack } : {})
        }
      };
      res.write(JSON.stringify(errorResponse) + '\n');
      res.end();
    }
  }

  private async handleNotificationsList(request: McpRequest): Promise<McpResponse> {
    this.logger.log('Returning notifications list (empty)');
    return {
      jsonrpc: "2.0",
      id: request.id,
      result: {
        notifications: []
      }
    };
  }

  private async initializeReadwise() {
    try {
      this.logger.info('Initializing Readwise MCP connection');
      await this.axios.post("/api/mcp/initialize");
      this.logger.info('Readwise MCP initialized successfully');
    } catch (error) {
      this.logger.error('Failed to initialize Readwise MCP', error);
    }
  }

  public start() {
    this.app.listen(this.port, '0.0.0.0', () => {
      this.logger.info(`🚀 Readwise MCP HTTP Server started successfully`);
      this.logger.info(`📖 Health check: http://localhost:${this.port}/health`);
      this.logger.info(`🔧 MCP endpoint: POST http://localhost:${this.port}/mcp`);
      this.logger.info(`📡 MCP streaming: POST http://localhost:${this.port}/mcp/stream`);
      this.logger.info(`ℹ️  MCP info: GET http://localhost:${this.port}/mcp/info`);
      this.logger.info(`🌐 Network accessible on all interfaces`);

      // Also log to console for immediate visibility
      console.log(`🚀 Readwise MCP HTTP Server running on port ${this.port}`);
      console.log(`📖 Health check: http://localhost:${this.port}/health`);
      console.log(`🔧 MCP endpoint: POST http://localhost:${this.port}/mcp`);
      console.log(`📡 MCP streaming: POST http://localhost:${this.port}/mcp/stream`);
      console.log(`ℹ️  MCP info: GET http://localhost:${this.port}/mcp/info`);
      console.log(`🌐 Network accessible on all interfaces`);
      console.log(`🔍 Debug mode: ${this.logger.debugMode ? 'enabled' : 'disabled'}`);
    });
  }
}

// Start the server
const server = new ReadwiseMcpHttpServer();
server.start();
