# Distributed under the terms of the MIT License

EAPI="7"

DESCRIPTION="A user-friendly time-traveling debugger for a wide range of programming languages"
HOMEPAGE="https://github.com/metacraft-labs/codetracer"
SRC_URI="$HOMEPAGE/releases/download/${PV}/resources.tar.xz -> resources.tar.xz
	https://downloads.codetracer.com/CodeTracer-${PV}-amd64.AppImage -> ct
"

LICENSE="AGPL-3"
SLOT="0"
KEYWORDS="*"
IUSE=""
RESTRICT=""

BDEPEND=""
DEPEND=""
RDEPEND="sys-fs/fuse
	dev-libs/openssl
	sys-apps/xdg-desktop-portal
"

src_unpack() {
	unpack "${A}"
}

src_install() {
	dobin "${WORKDIR}"/ct
	install "${WORKDIR}"/resources/codetracer.desktop "${ED}"/usr/share/applications/

	install "${WORKDIR}"/resources/Icon.iconset/icon_16x16.png "${ED}"/usr/share/icons/hicolor/16x16/apps/codetracer.png
	install "${WORKDIR}"/resources/Icon.iconset/icon_32x32.png "${ED}"/usr/share/icons/hicolor/32x32/apps/codetracer.png
	install "${WORKDIR}"/resources/Icon.iconset/icon_64x64.png "${ED}"/usr/share/icons/hicolor/64x64/apps/codetracer.png
	install "${WORKDIR}"/resources/Icon.iconset/icon_128x128.png "${ED}"/usr/share/icons/hicolor/128x128/apps/codetracer.png
	install "${WORKDIR}"/resources/Icon.iconset/icon_256x256.png "${ED}"/usr/share/icons/hicolor/256x256/apps/codetracer.png
	install "${WORKDIR}"/resources/Icon.iconset/icon_512x512.png "${ED}"/usr/share/icons/hicolor/512x512/apps/codetracer.png
}

