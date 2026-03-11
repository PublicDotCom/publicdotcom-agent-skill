# Public.com Agent Skill

## Overview

This is an agent skill for interacting with your Public.com brokerage account. You can get live quotes, place orders, get portfolio info, and more.

## Disclaimer

For illustrative and informational purposes only. Not investment advice or recommendations.

We recommend running this skill in as isolated of an environment as possible. If possible, test the integration on a new Public account as well.

## Before You Get Started

There are a few prerequisites needed to get started:

- **Python 3.8+** and **pip** — Required to run this skill. The skill's scripts use the `publicdotcom-py` SDK which will be auto-installed on first run.
- **Public.com account** — Create one at https://public.com/signup
- **Public.com API key** — Once you create your Public.com brokerage account, get an API key at https://public.com/settings/v2/api

## Configuration

This skill uses two environment variables:

| Variable | Required | Description |
|---|---|---|
| `PUBLIC_COM_SECRET` | Yes | Your Public.com API secret key |
| `PUBLIC_COM_ACCOUNT_ID` | No | Default account ID for all requests |

### Setting your API key

Set the environment variable before running your agent:

```bash
export PUBLIC_COM_SECRET=<YOUR_API_SECRET>
```

You can find your API secret at https://public.com/settings/v2/api. Alternatively, the skill will prompt you for it on first use (e.g. "How is my Public portfolio doing today?").

### Setting a default account ID

Some requests require an account ID. You can list your accounts first, then set a default:

```bash
export PUBLIC_COM_ACCOUNT_ID=<YOUR_ACCOUNT_ID>
```

This eliminates the need to specify `--account-id` on each command.

## Example Prompts

- How is my portfolio doing today?
- Can you get me the options chain for Nvidia for options expiring tomorrow?
- Can you get me the current quotes for Apple, Google, and Microsoft?
- Can you get my account history and list out and the deposits I've made?
- Set up a job to monitor the price of Bitcoin every 30 minutes. If the price is below $75K, buy $100 worth of it. If you are in a position and the price goes above $80K, sell it. All orders are market orders and only be in one position at a time. Run indefinitely.
- Get the options chain for Apple option contracts expiring Feb 18th. I want to open a call credit spread. Determine the best options contracts to do this with based on contract liquidity and max premium for cost.
