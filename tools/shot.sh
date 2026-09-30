#!/bin/sh
# 一站式截图：拉起 headless Chrome（调试端口 9222）-> CDP 截图 -> 关闭 Chrome。
# 必须整段跑在同一个 shell 进程里——本环境里后台进程会随命令结束被杀掉。
#
# 用法: sh tools/shot.sh <url> <out.png> [--width n] [--height n] [--wait ms] [--text file]
CHROME="${KAIRI_CHROME:-/c/Users/Administrator/.agent-browser/browsers/chrome-154.0.8037.57/chrome.exe}"
PORT="${KAIRI_CDP_PORT:-9222}"
PROF="/tmp/kairi_chrome_prof"
HERE="$(cd "$(dirname "$0")" && pwd)"

rm -rf "$PROF"
"$CHROME" --headless=new --no-sandbox --disable-gpu --hide-scrollbars \
  --remote-debugging-port="$PORT" --user-data-dir="$PROF" about:blank \
  > /tmp/kairi_chrome.log 2>&1 </dev/null &
CPID=$!

ready=0
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  code=$(curl -s --noproxy '*' -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/json/version" 2>/dev/null)
  if [ "$code" = "200" ]; then ready=1; break; fi
  sleep 1
done

if [ "$ready" != "1" ]; then
  echo "Chrome 调试端口未就绪，日志："
  head -20 /tmp/kairi_chrome.log
  kill "$CPID" 2>/dev/null
  exit 1
fi

node "$HERE/shot.mjs" "$@" --port "$PORT"
RC=$?

kill "$CPID" 2>/dev/null
rm -rf "$PROF"
exit $RC
