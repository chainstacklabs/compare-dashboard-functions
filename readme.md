# Chainstack dashboard functions

Serverless solution for monitoring RPC nodes latency across different blockchains and regions using Vercel Functions.

## Design

- Serverless functions run every minute in multiple regions
- Collects metrics from HTTP/WS endpoints for each blockchain
- Pushes metrics to Grafana Cloud

## Quick start

### Prerequisites
- Vercel account (check limits of your plan)
- Python 3.9+
- Grafana Cloud account

### Setup

1. Clone repository:
```bash
git clone <repository-url>
cd rpc-latency-monitor
```

2. Set environment variables in Vercel project (see `.env.example`)

3. Deploy to Vercel:
```bash
vercel deploy
```

### Local development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run development server:
```bash
vercel dev
```

3. Test endpoint:
```bash
curl http://localhost:3000/api/chains/ethereum
```

## Configuration

### Endpoints JSON format
```json
{
  "providers": [
    {
      "blockchain": "Ethereum",
      "name": "Provider1",
      "http_endpoint": "https://...",
      "websocket_endpoint": "wss://..."
    }
  ]
}
```

### Adding new blockchain
1. Create metric classes in `metrics/`
2. Register metrics in `api/chains/`
3. Update `vercel.json` with new endpoint
