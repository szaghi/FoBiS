// Default theme + client-side Mermaid rendering.
//
// The markdown fence hook in config.mts turns ```mermaid blocks into <pre class="mermaid">; here they are
// rendered with the `mermaid` package after each page load, and again when the dark mode toggles
// (vitepress-plugin-mermaid does the same, but does not support VitePress 2).
import DefaultTheme from 'vitepress/theme'
import { nextTick, onMounted, watch } from 'vue'
import { useData, useRoute } from 'vitepress'

async function renderMermaid(dark: boolean): Promise<void> {
  const nodes = Array.from(document.querySelectorAll<HTMLElement>('pre.mermaid'))
  if (!nodes.length) return
  const { default: mermaid } = await import('mermaid')
  mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: dark ? 'dark' : 'default' })
  for (const node of nodes) {
    node.dataset.source ??= node.textContent ?? ''  // keep the source: rendering replaces it with the SVG
    node.textContent = node.dataset.source
    node.removeAttribute('data-processed')
  }
  await mermaid.run({ nodes })
}

export default {
  extends: DefaultTheme,
  setup() {
    const route = useRoute()
    const { isDark } = useData()
    const render = () => nextTick(() => renderMermaid(isDark.value))
    onMounted(render)
    watch(() => route.path, render)
    watch(isDark, render)
  },
}
