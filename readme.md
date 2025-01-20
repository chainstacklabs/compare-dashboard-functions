# Public RPC Dashboard

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fchainstacklabs%2Fchainstack-rpc-dashboard-functions&env=GRAFANA_URL,GRAFANA_USER,GRAFANA_API_KEY,CRON_SECRET,ENDPOINTS,SKIP_AUTH,METRIC_NAME)

A serverless solution for monitoring RPC nodes response time across different blockchains and regions using Vercel Functions and Grafana Cloud. The project collects metrics from HTTP/WS endpoints for multiple blockchains and pushes them to Grafana Cloud for visualization.

📚 **[Public RPC Dashboard Documentation](https://docs.chainstack.com/docs/public-rpc-dashboard)**

## Features

- 🌐 Multi-region monitoring: US West, Germany, Singapore
- 📊 Real-time metrics visualization in [Grafana Cloud](https://chainstack.grafana.net/public-dashboards/65c0fcb02f994faf845d4ec095771bd0?orgId=1)
- 🔗 Support for multiple blockchains:
  - Ethereum
  - Base
  - Solana
  - TON

## Architecture

- Serverless functions run every minute in configured regions
- Metrics are collected and pushed to Grafana Cloud
- Authentication for production endpoints using `CRON_SECRET`
- Preview deployments for testing with `SKIP_AUTH`

## Deployment options

### 1. Single region quick deploy

1. Fork this repository
2. Click the "Deploy with Vercel" button above
3. Configure the required environment variables (see below)
4. Deploy!

### 2. Multi-region svetup

To monitor RPC providers from multiple regions:

1. Create three separate Vercel projects for different regions:
   - Project 1: `your-project-iad1` (US East)
   - Project 2: `your-project-sfo1` (US West)
   - Project 3: `your-project-hkg1` (Asia)

2. Link each project to the same repository

3. Configure region override in each project:
   - Project Settings → Functions → Function Region
   - Select the corresponding region (iad1/sfo1/hkg1)

4. Configure shared environment variables:
   - Team Settings → Environment Variables → Link To Projects

## Environment Variables

### Production Required Variables

```env
# Grafana Cloud configuration
GRAFANA_URL=https://influx-...-east-0.grafana.net/api/v1/push/influx/write
GRAFANA_USER=your_grafana_user_id
GRAFANA_API_KEY=your_grafana_api_key

# Monitoring configuration
METRIC_NAME=response_latency_seconds
METRIC_REQUEST_TIMEOUT=35
METRIC_MAX_LATENCY=35

# Security
CRON_SECRET=your_production_cron_secret  # Required for production
SKIP_AUTH=FALSE                          # Should be FALSE in production

# RPC configuration
ENDPOINTS={"providers":[{"blockchain":"Ethereum","name":"Provider1"...}]}
```

### Preview Environment Variables

For development and testing:

```env
METRIC_NAME=test_response_latency_seconds  # Add prefix to avoid metric conflicts
SKIP_AUTH=TRUE                            # Allows direct URL access
```

## Local Development

1. Clone and setup:
```bash
git clone https://github.com/chainstacklabs/chainstack-rpc-dashboard-functions.git
cd chainstack-rpc-dashboard-functions
```

2. Create and activate virtual environment:
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows
venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate
```

3. Configure environment:
```bash
cp .env.local.example .env.local   # Update with your values
cp endpoints.json.example endpoints.json
```

4. Install dependencies:
```bash
pip install -r requirements.txt
```

5. Run development server:
```bash
python run_local.py
```

6. Test endpoints:
```bash
curl http://localhost:8000/api/chains/ethereum
```

## RPC provider configuration

Configure your RPC providers in `endpoints.json`:

```json
{
    "providers": [
        {
            "blockchain": "Ethereum",
            "name": "Chainstack-Free",
            "region": "Global",
            "websocket_endpoint": "wss://ethereum-mainnet.core.chainstack.com/...",
            "http_endpoint": "https://ethereum-mainnet.core.chainstack.com/...",
            "data": {}
        }
    ]
}
```

## Project structure

```plaintext
.
├── api/                      # Vercel Serverless Functions
│   └── chains/              # Blockchain-specific handlers
│       ├── base.py          
│       ├── ethereum.py      
│       ├── solana.py        
│       └── ton.py           
├── common/                   # Shared utilities
│   ├── base_metric.py       # Base metric collection
│   ├── factory.py           # Metric factory pattern
│   ├── metric_config.py     # Configuration classes
│   ├── metric_types.py      # Metric type definitions
│   └── metrics_handler.py   # Core metrics handler
├── metrics/                  # Blockchain-specific metrics
│   ├── base.py              
│   ├── ethereum.py          
│   ├── solana.py            
│   └── ton.py               
└── config files...          # Configuration and setup files
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/YourFeature`)
3. Commit your changes (`git commit -am 'Add YourFeature'`)
4. Push to the branch (`git push origin feature/YourFeature`)
5. Create a Pull Request
