import { Component, ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

/** 全局错误边界：捕获渲染期的 React 错误，避免整个应用白屏崩溃。 */
export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('React 错误边界捕获:', error, errorInfo)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen items-center justify-center bg-gray-50">
          <div className="max-w-md rounded-2xl bg-white p-8 text-center shadow-lg">
            <div className="mb-4 text-5xl">😵</div>
            <h1 className="mb-2 text-xl font-bold text-gray-800">
              页面出错了
            </h1>
            <p className="mb-6 text-sm text-gray-500">
              应用遇到了意外错误，请刷新页面重试。
            </p>
            {this.state.error && (
              <pre className="mb-6 max-h-32 overflow-auto rounded-lg bg-gray-100 p-3 text-left text-xs text-gray-600">
                {this.state.error.message}
              </pre>
            )}
            <button
              onClick={this.handleReset}
              className="rounded-xl bg-blue-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-700"
            >
              刷新页面
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
