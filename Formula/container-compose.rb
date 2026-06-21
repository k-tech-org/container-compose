class ContainerCompose < Formula
  include Language::Python::Virtualenv

  desc "Docker Compose compatibility wrapper for Apple's container CLI"
  homepage "https://github.com/k-tech-org/container-compose"
  url "https://github.com/k-tech-org/container-compose/releases/download/v0.1.0/container_compose-0.1.0.tar.gz"
  sha256 "f63474821d893e81843705dbf1c82384f97ff0e777b739b4df5d277b8a3cb172"
  license "MIT"

  depends_on "libyaml"
  depends_on "python@3.14"

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/05/8e/961c0007c59b8dd7729d542c61a4d537767a59645b82a0b521206e1e25c2/pyyaml-6.0.3.tar.gz"
    sha256 "d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f"
  end

  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      container-compose requires Apple's container CLI 1.0+.

      Start the container service before running Compose projects:
        container system start
    EOS
  end

  test do
    assert_match "Usage: container-compose", shell_output("#{bin}/container-compose --help")
  end
end
