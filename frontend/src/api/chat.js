import { getToken } from '@/utils/session'

/**
 * SSE 流式对话（fetch + ReadableStream）
 * onChunk(chunk): 每收到一帧调用；chunk.done=true 时流结束
 * onError(err): 网络或解析错误回调
 */
export async function streamChat(payload, onChunk, onError) {
  const token = getToken()
  let res
  try {
    res = await fetch('/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    })
  } catch (err) {
    onError(err)
    return
  }

  if (!res.ok) {
    onError(new Error(`HTTP ${res.status}`))
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  try {
    let receivedDone = false
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        if (!receivedDone) onError(new Error('对话连接意外结束'))
        break
      }
      buf += decoder.decode(value, { stream: true })
      const parts = buf.split('\n\n')
      buf = parts.pop() // 保留不完整帧
      for (const part of parts) {
        if (!part.startsWith('data: ')) continue
        try {
          const chunk = JSON.parse(part.slice(6))
          onChunk(chunk)
          if (chunk.done) {
            receivedDone = true
            return
          }
        } catch {
          // 忽略 JSON 解析失败的单帧
        }
      }
    }
  } catch (err) {
    onError(err)
  }
}

export async function uploadChatFile(file, fileType) {
  const formData = new FormData()
  formData.append('file', file)
  const token = getToken()
  const res = await fetch(`/api/chat/upload?file_type=${encodeURIComponent(fileType)}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  })
  const body = await res.json()
  if (!res.ok || body.code !== 0) throw new Error(body.msg || '附件上传失败')
  return body.data
}
