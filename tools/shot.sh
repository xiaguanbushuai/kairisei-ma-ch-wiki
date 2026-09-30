#!/bin/sh
# 一站式截图：拉起 headless Chrome（调试端口 9222）-> CDP 截图 -> 关闭 Chrome。
# 必须整段跑在同一个 shell 进程里——本环境里后台进程会随命令结束被杀掉。
#
# 用法: sh tools/shot.sh <url> <out.png> [--width n] [--height n] [--wait ms] [--text file]
# 浏览器路径：优先 KAIRI_CHROME 环境变量，其次自动探测常见安装位置。
find_chrome() {
  if [ -n "$KAIRI_CHROME" ]; then printf '%s' "$KAIRI_CHROME"; return; fi
  for c in "$HOME"/.agent-browser/browsers/*/chrome.exe \
           "/c/Program Files/Google/Chrome/Application/chrome.exe" \
           "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
           "$LOCALAPPDATA/Google/Chrome/Application/chrome.exe"; do
    [ -f "$c" ] && { printf '%s' "$c"; return; }
  done
  command -v google-chrome 2>/dev/null || command -v chromium 2>/dev/null
}
CHROME="$(find_chrome)"
if [ -z "$CHROME" ] || [ ! -f "$CHROME" ]; then
  echo "未找到 Chrome，请用 KAIRI_CHROME=<chrome.exe 完整路径> 指定。"
  exit 1
fi
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
