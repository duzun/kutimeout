# Maintainer: Dumitru Uzun <duzun@example.com>
pkgname=kutimeout
pkgver=0.0.1
pkgrel=1
pkgdesc="A KDE Plasma session manager that limits daily computer usage and automatically logs out the user"
arch=('any')
url="https://github.com/duzun/kutimeout"
license=('MIT')
depends=('python' 'qt5-tools' 'libnotify')
optdepends=('plasma-desktop: for KDE session management')
install=kutimeout.install

# We'll use local files as the source for now
source=("kutimeout.py" "kutimeout.desktop" "README.md" "LICENSE")
sha256sums=('SKIP' 'SKIP' 'SKIP' 'SKIP')

# To generate real checksums before uploading to AUR:
# source=("${pkgname}-${pkgver}.tar.gz::${url}/archive/v${pkgver}.tar.gz")
# sha256sums=('...')

package() {
  # Install main script
  install -Dm755 "$srcdir/kutimeout.py" "$pkgdir/usr/share/kutimeout/kutimeout.py"

  # Create symlink in /usr/bin
  mkdir -p "$pkgdir/usr/bin"
  ln -s /usr/share/kutimeout/kutimeout.py "$pkgdir/usr/bin/kutimeout"

  # Install locale files from the local directory
  if [ -d "$startdir/locale" ]; then
    mkdir -p "$pkgdir/usr/share/kutimeout/locale"
    cp -r "$startdir/locale"/* "$pkgdir/usr/share/kutimeout/locale/"
  fi

  # Install desktop file for autostart
  install -Dm644 "$srcdir/kutimeout.desktop" "$pkgdir/etc/xdg/autostart/kutimeout.desktop"

  # Install README and LICENSE
  install -Dm644 "$srcdir/README.md" "$pkgdir/usr/share/doc/$pkgname/README.md"
  install -Dm644 "$srcdir/LICENSE" "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
