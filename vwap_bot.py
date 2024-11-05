import discord
from discord.ext import commands, tasks
import requests
from dotenv import load_dotenv
import os
import json
from datetime import datetime, timezone, timedelta

# Load environment variables from .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Set up intents
intents = discord.Intents.default()
intents.message_content = True

# Initialize the bot with intents
bot = commands.Bot(command_prefix="!", intents=intents)

# Dictionary to store coin alerts with contract addresses and VWAP levels
price_alerts = {}

# File to store alerts
ALERTS_FILE = 'alerts.json'

def save_alerts():
    """Saves the current alerts to a JSON file."""
    with open(ALERTS_FILE, 'w') as f:
        json.dump(price_alerts, f, default=str)  # Use default=str to handle datetime serialization

def load_alerts():
    """Loads alerts from a JSON file."""
    global price_alerts
    try:
        with open(ALERTS_FILE, 'r') as f:
            price_alerts = json.load(f)
            # Convert string timestamps back to datetime objects
            for alert in price_alerts.values():
                if alert['last_alert_time']:
                    alert['last_alert_time'] = datetime.fromisoformat(alert['last_alert_time'])
    except FileNotFoundError:
        price_alerts = {}

@bot.command()
async def vwap(ctx, contract_address: str, vwap_level: float):
    """
    Adds a token to the watch list using the contract address, selects the top trading pair,
    and sets a VWAP level alert within ±10%.
    """
    contract_address = contract_address.lower()
    top_pairs = fetch_top_pairs(contract_address, top_n=5)
    
    if top_pairs:
        # Choose the highest liquidity pair
        top_pair = top_pairs[0]
        ticker = top_pair['baseToken']['symbol']
        current_price = float(top_pair['priceUsd'])
        market_cap = top_pair.get('marketCap', 'N/A')
        liquidity = top_pair['liquidity']['usd']
        fdv = top_pair.get('fdv', 'N/A')
        chain = top_pair['chainId']
        dex = top_pair['dexId']
        age_days = calculate_age(top_pair['pairCreatedAt'])

        # Create an embed message
        embed = discord.Embed(
            title=f"{ticker} / {top_pair['quoteToken']['symbol']} ⬆︎",
            url=top_pair['url'],
            description=f"**Contract:** `{contract_address}`\n"
                        f"**Chain:** {chain.capitalize()} @ {dex.capitalize()}",
            color=0x1ABC9C,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Adding fields
        embed.add_field(name="💰 USD Price", value=f"${current_price:,.5f}", inline=True)
        embed.add_field(name="💎 FDV", value=f"${int(fdv):,}" if isinstance(fdv, (int, float)) else fdv, inline=True)
        embed.add_field(name="💦 Liquidity", value=f"${int(liquidity):,}", inline=True)
        
        # Trading and historical information
        embed.add_field(name="📊 Volume (24h)", value=f"${top_pair['volume']['h24']:,.2f}", inline=True)
        embed.add_field(name="🕰️ Age", value=f"{age_days}d", inline=True)
        embed.add_field(name="⛰️ ATH", value=f"${top_pair['marketCap']*2:,.1f} (est)", inline=True)  # example estimation
        
        # One-hour price change, transactions, and market status
        embed.add_field(
            name="📈 1H Change",
            value=f"{top_pair['priceChange']['h1']}% ⋅ ${top_pair['volume']['h1']:,.1f} 🅑 {top_pair['txns']['h1']['buys']} 🅢 {top_pair['txns']['h1']['sells']}",
            inline=False
        )

        # Set VWAP level alert
        price_alerts[contract_address] = {
            'vwap_level': vwap_level,
            'ticker': ticker,
            'current_price': current_price,
            'user': ctx.author.display_name,
            'profile_pic': ctx.author.display_avatar.url,
            'last_alert_time': None  # To track the last alert time for 24-hour restriction
        }
        save_alerts()  # Save alerts after adding a new one
        alert_msg = f"Alert set: Notify when price is within ±10% of VWAP level ${vwap_level}"
        embed.add_field(name="📌 Alert", value=alert_msg, inline=False)
        
        # Set embed footer and author information
        embed.set_footer(text="Data from DexScreener")
        embed.set_thumbnail(url=top_pair['info']['imageUrl'])
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)

        await ctx.send(embed=embed)
    else:
        await ctx.send(f"No trading pairs found for contract {contract_address}. Please verify the address.")

@tasks.loop(minutes=1)
async def monitor_prices():
    """
    Periodically checks prices for each token in the watch list
    and sends an alert if the price is within ±10% of the VWAP level,
    with a restriction to only send one alert per 24 hours.
    """
    for contract_address, alert_data in price_alerts.items():
        token_data = fetch_token_pairs(contract_address)
        
        if token_data and 'pairs' in token_data:
            current_price = float(token_data['pairs'][0]['priceUsd'])
            ticker = alert_data['ticker']
            alert_data['current_price'] = current_price

            print(f"Checking price for {ticker}: ${current_price}")  # Log current price

            # Check VWAP level range
            vwap_level = alert_data['vwap_level']
            lower_bound = vwap_level * 0.9
            upper_bound = vwap_level * 1.1
            
            # Calculate the absolute and percentage differences
            difference = current_price - vwap_level
            percentage_difference = (difference / vwap_level) * 100

            # Check if current price is within the VWAP range and if 24 hours have passed since the last alert
            if lower_bound <= current_price <= upper_bound:
                last_alert_time = alert_data.get('last_alert_time')
                if last_alert_time is None or (datetime.now(timezone.utc) - last_alert_time) >= timedelta(days=1):
                    # Update last alert time
                    alert_data['last_alert_time'] = datetime.now(timezone.utc)
                    save_alerts()  # Save alerts after updating the last alert time
                    await send_alert_message(
                        f"{ticker} is near the VWAP!\n\nCurrent price: ${current_price:.2f} ({percentage_difference:+.2f}%)",
                        alert_data['user'],
                        alert_data['profile_pic']
                    )
        else:
            print(f"Data not found for contract {contract_address}")  # Log if no data is found

async def send_alert_message(message, user, profile_pic):
    """
    Sends a message to the 'price-alerts' channel in Discord with user context and tags the @vwap role.
    """
    # Replace ROLE_ID with the actual ID of the @vwap role
    vwap_role_id = "1302956931840737412"  # Example: "123456789012345678"
    
    channel = discord.utils.get(bot.get_all_channels(), name="price-alerts")
    if channel:
        # Embed the message content
        embed = discord.Embed(description=message, color=0xE74C3C, timestamp=datetime.now(timezone.utc))
        embed.set_author(name=user, icon_url=profile_pic)  # Show who set the alert

        # Send the message tagging @vwap role
        await channel.send(content=f"<@&{vwap_role_id}>", embed=embed)
    else:
        print("No 'price-alerts' channel found.")

@bot.command()
async def list_alerts(ctx):
    """
    Lists all the current alerts set by users.
    """
    if price_alerts:
        alert_list = "\n".join(
            [f"{data['ticker']} (VWAP: ${data['vwap_level']}, Last Alert: {data['last_alert_time']})" 
             for data in price_alerts.values()]
        )
        await ctx.send(f"**Current Alerts:**\n{alert_list}")
    else:
        await ctx.send("No alerts are currently set.")

@bot.command()
async def remove_token(ctx, contract_address: str):
    """
    Removes a specified token's alert by its contract address.
    """
    contract_address = contract_address.lower()
    if contract_address in price_alerts:
        del price_alerts[contract_address]
        save_alerts()  # Save alerts after removing one
        await ctx.send(f"Alert for contract {contract_address} has been removed.")
    else:
        await ctx.send(f"No alert found for contract {contract_address}.")

def fetch_top_pairs(contract_address, top_n=5):
    """
    Retrieves top trading pairs for a given token address, sorted by liquidity.
    """
    url = f"https://api.dexscreener.com/latest/dex/tokens/{contract_address}"
    response = requests.get(url)
    if response.status_code == 200:
        pairs = response.json().get('pairs', [])
        
        # Filter pairs with liquidity info and sort by liquidity
        pairs_with_liquidity = [pair for pair in pairs if 'liquidity' in pair and 'usd' in pair['liquidity']]
        sorted_pairs = sorted(pairs_with_liquidity, key=lambda x: x['liquidity']['usd'], reverse=True)
        
        # Return only the top N pairs
        return sorted_pairs[:top_n]
    else:
        print(f"Failed to retrieve pairs for contract {contract_address}")
        return None

def calculate_age(timestamp):
    """
    Calculates the age in days from a timestamp.
    """
    now = datetime.now(timezone.utc)
    created_at = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
    return (now - created_at).days

def fetch_token_pairs(contract_address):
    """
    Fetches all available trading pairs for a given token address.
    """
    url = f"https://api.dexscreener.com/latest/dex/tokens/{contract_address}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    print(f"Failed to retrieve data for contract {contract_address}. Status code: {response.status_code}")
    return None

@bot.event
async def on_ready():
    """
    Called when the bot is ready. Starts the price-monitoring loop and loads saved alerts.
    """
    print(f"Bot is online as {bot.user}")
    load_alerts()  # Load alerts from file
    if not monitor_prices.is_running():
        monitor_prices.start()
        print("Price monitoring has started")

# Run the bot
bot.run(TOKEN)
