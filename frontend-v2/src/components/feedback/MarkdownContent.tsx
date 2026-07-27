import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function MarkdownContent({ content }: { content: string }) {
  if (!content.trim()) return <p className="muted">当前数据集没有可展示的画像报告。</p>
  return <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{content}</ReactMarkdown></div>
}
