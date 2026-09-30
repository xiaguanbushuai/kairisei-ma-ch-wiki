<script setup>
import { onMounted, ref } from 'vue'
import { getMeta } from './api.js'

const theme = ref(localStorage.getItem('kairi-theme') || 'dark')
const meta = ref(null)

function applyTheme(value) {
  document.documentElement.dataset.theme = value
  localStorage.setItem('kairi-theme', value)
}

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  applyTheme(theme.value)
}

onMounted(async () => {
  applyTheme(theme.value)
  try {
    meta.value = await getMeta()
  } catch (error) {
    console.error(error)
  }
})
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="topbar-inner">
        <router-link to="/" class="brand">
          <span class="brand-mark">MA</span>
          <span>
            乖离性百万亚瑟王
            <span class="brand-sub">国服资料站</span>
          </span>
        </router-link>

        <nav class="nav">
          <router-link class="nav-link" to="/cards">卡牌</router-link>
          <router-link class="nav-link" to="/skills">技能</router-link>
          <router-link class="nav-link" to="/bosses">Boss</router-link>
          <router-link class="nav-link" to="/items">道具</router-link>
        </nav>

        <button class="theme-toggle" :title="theme === 'dark' ? '切换到浅色' : '切换到深色'" @click="toggleTheme">
          {{ theme === 'dark' ? '☀' : '☾' }}
        </button>
      </div>
    </header>

    <main class="main">
      <router-view />
    </main>

    <footer class="footer">
      <div v-if="meta">
        数据版本：{{ meta.generated }} · 卡牌 {{ meta.counts.cards.toLocaleString() }} 张 ·
        技能 {{ meta.counts.skills.toLocaleString() }} 条 · Boss {{ meta.counts.bosses.toLocaleString() }} 个 ·
        道具 {{ meta.counts.items.toLocaleString() }} 项
      </div>
      <div>
        本站为非盈利的资料整理站点，数据来自《乖离性百万亚瑟王》国服客户端资源，仅用于学习与怀旧交流。
        游戏内容版权归原权利方所有。
      </div>
    </footer>
  </div>
</template>
