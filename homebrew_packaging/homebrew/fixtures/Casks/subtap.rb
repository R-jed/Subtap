cask "subtap" do
  arch arm: "arm64"

  version "0.1.0"
  sha256 :no_check # TODO: CI 填充真实 SHA256

  # TODO: CI 填充发布产物 URL（GitHub Release 或自建 CDN）
  url "https://github.com/anthropics/subtap/releases/download/v#{version}/subtap-#{version}-macos-arm64.tar.gz"
  name "subtap"
  desc "Local-first TUI subtitle tool with plugin-based ASR/LLM/Aligner pipeline"
  homepage "https://github.com/anthropics/subtap"

  depends_on arch: :arm64
  depends_on macos: ">=14"

  binary "subtap/bin/subtap"

  uninstall delete: [
    "#{staged_path}/subtap",
  ]
  # 不声明 zap，保留 ~/.subtap 用户数据（glossary、配置等）
end
