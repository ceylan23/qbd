import os
import requests
import time
from datetime import datetime
from solana.rpc.api import Client
from solders.pubkey import Pubkey

# ================= 配置区 =================
WXPUSHER_TOKEN = os.environ.get("WXPUSHER_TOKEN", "AT_rxQeEODPHi486whj9HeohAUHNLupSLJD")
TOPIC_ID = 42641

ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
BSCSCAN_API_KEY = os.environ.get("BSCSCAN_API_KEY", "")

# EVM 链配置 (以太坊 + BSC)
EVM_NETWORKS = {
    "Ethereum": {"url": "https://api.etherscan.io/api", "key": ETHERSCAN_API_KEY, "explorer": "etherscan.io"},
    "BSC": {"url": "https://api.bscscan.com/api", "key": BSCSCAN_API_KEY, "explorer": "bscscan.com"}
}

# 待监控的 EVM 钱包地址
EVM_WALLETS = [
    "0x2affb7f6c7f666043a5418dc4cb0b4f80bc767bd",
    "0x61e6b4c6a170b59fd6c8966e545d740ce34b409d",
    "0xf29f0a86420399f662577b68c48137d510084d96",
    "0xad28d976ae024c03f6cccc5806e5224364048b71",
    "0xd8f49165098943d450a52bd58d1b5de0d60d9ffd",
    "0x7ad3c2303655f78594e4f976ddb873aef9322efc",
    "0x31acb6dc0c018950632697de37344cc33cfcd3e6",
    "0x4f8633ddae2f74ea0e31468f58376f338f1b2550",
    "0xb12744a3083e8f010421a7d3d57f8acbce995c7f"
]

# 待监控的 Solana 钱包地址 (Base58格式)
SOL_WALLETS = [
    "vines1vzrYbzLMRdu58ou5XTby4qAqVRLmqo36NKPTg"
]

CHECK_INTERVAL_SECONDS = 30 * 60 
# ==========================================

def get_token_info(token_address):
    try:
        res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_address}").json()
        if res.get('pairs'):
            pair = res['pairs'][0]
            buys = pair.get('txns', {}).get('h24', {}).get('buys', 0)
            sells = pair.get('txns', {}).get('h24', {}).get('sells', 0)
            volume = pair.get('volume', {}).get('h24', 0)
            
            if volume > 500000 and buys > sells:
                heat = "🔥🔥🔥 极高热度 (资金净流入)"
            elif volume > 50000:
                heat = "🔥 中等热度 (温和交易)"
            else:
                heat = "❄️ 低热度 (注意风险)"
                
            return {
                "symbol": pair.get('baseToken', {}).get('symbol', 'Unknown'),
                "price": pair.get('priceUsd', '0'),
                "heat": heat,
                "url": pair.get('url', '')
            }
    except Exception as e:
        print(f"DexScreener API 请求失败: {e}")
    return None

def send_wxpusher(html_content, summary):
    payload = {
        "appToken": WXPUSHER_TOKEN, 
        "content": html_content, 
        "summary": summary,
        "contentType": 2, 
        "topicIds": [TOPIC_ID]
    }
    requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload)

def check_evm_networks(start_time):
    for net_name, config in EVM_NETWORKS.items():
        if not config['key']:
            print(f"⚠️ 未配置 {net_name} 的 API KEY，跳过。")
            continue
            
        print(f"🌐 正在扫描 {net_name} 网络...")
        for wallet in EVM_WALLETS:
            url = f"{config['url']}?module=account&action=tokentx&address={wallet}&page=1&offset=10&sort=desc&apikey={config['key']}"
            try:
                res = requests.get(url).json()
                if res.get('status') != '1' or not res.get('result'):
                    continue
                    
                for tx in res['result']:
                    tx_time = int(tx['timeStamp'])
                    if tx_time < start_time: break
                    
                    action = "买入/收到" if tx['to'].lower() == wallet.lower() else "卖出/发送"
                    color = "#4CAF50" if action == "买入/收到" else "#F44336"
                    token_symbol = tx['tokenSymbol']
                    amount = float(tx['value']) / (10 ** int(tx['tokenDecimal']))
                    
                    print(f"🚨 {net_name} 异动: {wallet[:6]}... {action} {amount} {token_symbol}")
                    token_info = get_token_info(tx['contractAddress'])
                    
                    dt_str = datetime.fromtimestamp(tx_time).strftime('%Y-%m-%d %H:%M:%S')
                    html = f"<h2>🚨 聪明钱包异动 ({net_name})</h2><p><strong>🕒 时间：</strong>{dt_str}</p><p><strong>💼 钱包：</strong>{wallet}</p><h3 style='color:{color};'>➡️ {action} {amount:,.4f} {token_symbol}</h3>"
                    
                    if token_info:
                        html += f"<ul><li>价格：${token_info['price']}</li><li>热度：{token_info['heat']}</li></ul><p><a href='{token_info['url']}'>点击查看 DexScreener</a></p>"
                    
                    send_wxpusher(html, f"[{net_name}] {wallet[:4]}.. {action} {token_symbol}")
                    time.sleep(1)
            except Exception as e:
                print(f"{net_name} 钱包 {wallet} 查询出错: {e}")

def check_solana(start_time):
    print(f"🌐 正在扫描 Solana 网络...")
    try:
        client = Client("https://api.mainnet-beta.solana.com")
        for wallet in SOL_WALLETS:
            try:
                pubkey = Pubkey.from_string(wallet)
                response = client.get_signatures_for_address(pubkey, limit=5)
                if not response.value: continue
                
                for sig_info in response.value:
                    tx_time = sig_info.block_time
                    if not tx_time or tx_time < start_time: break
                    
                    print(f"🚨 Solana 异动: {wallet[:6]}... 发生新交易！")
                    
                    dt_str = datetime.fromtimestamp(tx_time).strftime('%Y-%m-%d %H:%M:%S')
                    html = f"<h2>🚨 聪明钱包异动 (Solana 🟣)</h2>"
                    html += f"<p><strong>🕒 时间：</strong>{dt_str}</p>"
                    html += f"<p><strong>💼 钱包：</strong>{wallet}</p>"
                    html += f"<h3 style='color:#9C27B0;'>➡️ 发生新链上交互！</h3>"
                    html += f"<p>💡 <a href='https://solscan.io/tx/{sig_info.signature}'>👉 点击前往 Solscan 浏览器查看详情</a></p>"
                    
                    send_wxpusher(html, f"[Solana] {wallet[:4]}.. 发生新交易")
                    time.sleep(1)
            except Exception as e:
                print(f"Solana 钱包 {wallet} 查询出错: {e}")
    except Exception as e:
        print(f"Solana 客户端初始化失败: {e}")

if __name__ == "__main__":
    current_time = int(time.time())
    start_time = current_time - CHECK_INTERVAL_SECONDS
    
    check_evm_networks(start_time)
    check_solana(start_time)
