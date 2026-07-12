class Subtap < Formula
  include Language::Python::Virtualenv

  desc "Local-first TUI subtitle tool with plugin-based ASR/LLM/Aligner pipeline"
  homepage "https://github.com/anthropics/subtap"
  # TODO: fill in URL and SHA256 from brew create --python
  url "https://files.pythonhosted.org/packages/source/s/subtap/subtap-0.1.0.tar.gz"
  sha256 "PLACEHOLDER_SHA256"
  license "MIT"

  depends_on arch: :arm64
  depends_on "python@3.12"
  depends_on "ffmpeg"

  # TODO: fill in URL and SHA256 from brew update-python-resources

  # Core dependencies
  resource "typer" do
    url "https://files.pythonhosted.org/packages/source/t/typer/typer-0.9.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "pydantic" do
    url "https://files.pythonhosted.org/packages/source/p/pydantic/pydantic-2.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/source/P/PyYAML/PyYAML-6.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "pydub" do
    url "https://files.pythonhosted.org/packages/source/p/pydub/pydub-0.25.1.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/source/r/rich/rich-13.0.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "textual" do
    url "https://files.pythonhosted.org/packages/source/t/textual/textual-0.80.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "httpx" do
    url "https://files.pythonhosted.org/packages/source/h/httpx/httpx-0.27.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "python-docx" do
    url "https://files.pythonhosted.org/packages/source/p/python-docx/python-docx-1.0.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "openpyxl" do
    url "https://files.pythonhosted.org/packages/source/o/openpyxl/openpyxl-3.0.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "rapidfuzz" do
    url "https://files.pythonhosted.org/packages/source/r/rapidfuzz/rapidfuzz-3.0.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "jieba" do
    url "https://files.pythonhosted.org/packages/source/j/jieba/jieba-0.42.1.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "silero-vad" do
    url "https://files.pythonhosted.org/packages/source/s/silero-vad/silero-vad-6.2.1.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "onnxruntime" do
    url "https://files.pythonhosted.org/packages/source/o/onnxruntime/onnxruntime-1.24.3.tar.gz"
    sha256 "PLACEHOLDER"
  end

  # ARM64-only dependencies (MLX)
  resource "mlx" do
    url "https://files.pythonhosted.org/packages/source/m/mlx/mlx-0.31.1.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "mlx-audio" do
    url "https://files.pythonhosted.org/packages/source/m/mlx-audio/mlx-audio-0.4.3.tar.gz"
    sha256 "PLACEHOLDER"
  end

  def install
    virtualenv_install_with_resources

    bin.install_symlink libexec/"bin/subtap"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/subtap version")
    assert_match '"ok"', shell_output("#{bin}/subtap doctor --json", 1)
  end
end
