import os
import requests
import time
from datetime import datetime
import json

# ================= 配置区 =================
# WxPusher 配置
WXPUSHER_TOKEN = os.environ.get("WXPUSHER_TOKEN", "AT_rxQeEODPHi486whj9HeohAUHNLupSLJD")
TOPIC_ID = 42641

# Etherscan API Key (免费申请: https://etherscan.io/apis)
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "你的ETHERSCAN_API_KEY")

# 待监控的 9 个钱包地址 (从你的 gl.txt 提取去重)
WALLETS = [
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

# 检查过去多长时间内的交易？(这里设置30分钟，单位秒，需与 GitHub Actions 定时一致)
CHECK_INTERVAL_SECONDS = 30 * 60 
# ==========================================

def get_token_info(token_address):
    """通过 DexScreener 查询代币的热度、市值等信息"""
    url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
    try:
        res = requests.get(url).json()
        if res.get('pairs'):
            pair = res['pairs'][0]
            buys = pair.get('txns', {}).get('h24', {}).get('buys', 0)
            sells = pair.get('txns', {}).get('h24', {}).get('sells', 0)
            volume = pair.get('volume', {}).get('h24', 0)
            
            # 简单判断热度
            if volume > 500000 and buys > sells:
                heat = "🔥🔥🔥 极高热度 (大资金买入)"
            elif volume > 50000:
                heat = "🔥 中等热度 (温和交易)"
            else:
                heat = "❄️ 低热度 (流动性差，注意风险)"
                
            return {
                "name": pair.get('baseToken', {}).get('name', 'Unknown'),
                "symbol": pair.get('baseToken', {}).get('symbol', 'Unknown'),
                "price": pair.get('priceUsd', '0'),
                "liquidity": pair.get('liquidity', {}).get('usd', 0),
                "heat": heat,
                "url": pair.get('url', '')
            }
    except Exception as e:
        print(f"获取代币 {token_address} 数据失败: {e}")
    return None

def send_wxpusher(html_content, summary):
    """推送到 WxPusher"""
    url = "https://wxpusher.zjiecode.com/api/send/message"
    payload = {
        "appToken": WXPUSHER_TOKEN,
        "content": html_content,
        "summary": summary,
        "contentType": 2, # HTML 格式
        "topicIds": [TOPIC_ID]
    }
    requests.post(url, json=payload)

def monitor_wallets():
    print(f"🔍 正在查询 {len(WALLETS)} 个钱包在过去 {CHECK_INTERVAL_SECONDS/60} 分钟内的动向...")
    current_time = int(time.time())
    start_time = current_time - CHECK_INTERVAL_SECONDS

    for wallet in WALLETS:
        # 使用 Etherscan API 获取该钱包近期的 ERC-20 代币转账记录
        url = (f"https://api.etherscan.io/api?module=account&action=tokentx"
               f"&address={wallet}&page=1&offset=20&sort=desc&apikey={ETHERSCAN_API_KEY}")
        
        try:
            res = requests.get(url).json()
            if res['status'] != '1' or not res['result']:
                continue
                
            for tx in res['result']:
                tx_time = int(tx['timeStamp'])
                if tx_time < start_time:
                    break # 交易太老了，跳过后续（因为按时间倒序排列）
                
                # 判断是买入(收币)还是卖出(发币)
                action = "买入/收到" if tx['to'].lower() == wallet.lower() else "卖出/发送"
                color = "#4CAF50" if action == "买入/收到" else "#F44336"
                
                token_symbol = tx['tokenSymbol']
                token_address = tx['contractAddress']
                # 转换代币精度
                amount = float(tx['value']) / (10 ** int(tx['tokenDecimal']))
                
                print(f"🚨 发现异动: {wallet[:6]}... {action} {amount} {token_symbol}")
                
                # 查一下这个币是什么来头
                token_info = get_token_info(token_address)
                
                # 组装微信推送消息
                dt_str = datetime.fromtimestamp(tx_time).strftime('%Y-%m-%d %H:%M:%S')
                html = f"""
                <h2>🚨 聪明钱包异动监控</h2>
                <p><strong>🕒 时间：</strong>{dt_str}</p>
                <p><strong>💼 钱包：</strong>{wallet}</p>
                <hr/>
                <h3 style="color:{color};">➡️ 动作：{action} {amount:,.4f} {token_symbol}</h3>
                """
                
                if token_info:
                    html += f"""
                    <hr/>
                    <h3>📊 代币分析 ({token_info['symbol']})</h3>
                    <ul>
                        <li><strong>当前价格：</strong> ${token_info['price']}</li>
                        <li><strong>池子流动性：</strong> ${token_info['liquidity']:,.0f}</li>
                        <li><strong>市场热度：</strong> {token_info['heat']}</li>
                    </ul>
                    <p>💡 <a href="{token_info['url']}">点击查看 DexScreener K线图</a></p>
                    """
                else:
                    html += f"<p>⚠️ 未在 DexScreener 找到该代币数据 (可能是新币或无流动性)</p>"
                    
                summary_text = f"钱包 {wallet[:4]}.. {action} {token_symbol}"
                send_wxpusher(html, summary_text)
                
                # 稍微休眠，防止触发 API 限流
                time.sleep(1)
                
        except Exception as e:
            print(f"钱包 {wallet} 查询出错: {e}")
            
if __name__ == "__main__":
    if ETHERSCAN_API_KEY == "你的ETHERSCAN_API_KEY":
        print("⚠️ 警告：你还没有设置 ETHERSCAN_API_KEY，可能无法获取交易数据！")
    monitor_wallets()
