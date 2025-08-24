# Distributed under the terms of the MIT License

EAPI="7"

DESCRIPTION="A user-friendly time-traveling debugger for a varierty of programming languages"
HOMEPAGE="https://github.com/metacraft-labs/codetracer"
SRC_URI="$HOMEPAGE/releases/download/${PV}/resources.tar.xz -> resources.tar.xz
https://downloads.codetracer.com/CodeTracer-${PV}-amd64.AppImage -> ct"

LICENSE="AGPL-3"
SLOT="0"
KEYWORDS="*"
IUSE=""
RESTRICT="strip" # Stripping ct will make it unable to be run

BDEPEND=""
DEPEND=""
RDEPEND="sys-fs/fuse
	dev-libs/openssl
	sys-apps/xdg-desktop-portal
"

S="${WORKDIR}/"

src_unpack() {
	unpack resources.tar.xz
	cp "${DISTDIR}"/ct "${WORKDIR}"
}

src_install() {
	dobin "${WORKDIR}"/ct

	install -Dm644 "${WORKDIR}"/resources/codetracer.desktop "${ED}"/usr/share/applications/codetracer.desktop

	install -Dm644 "${WORKDIR}"/resources/Icon.iconset/icon_16x16.png "${ED}"/usr/share/icons/hicolor/16x16/apps/codetracer.png
	install -Dm644 "${WORKDIR}"/resources/Icon.iconset/icon_32x32.png "${ED}"/usr/share/icons/hicolor/32x32/apps/codetracer.png
	install -Dm644 "${WORKDIR}"/resources/Icon.iconset/icon_128x128.png "${ED}"/usr/share/icons/hicolor/128x128/apps/codetracer.png
	install -Dm644 "${WORKDIR}"/resources/Icon.iconset/icon_256x256.png "${ED}"/usr/share/icons/hicolor/256x256/apps/codetracer.png
	install -Dm644 "${WORKDIR}"/resources/Icon.iconset/icon_512x512.png "${ED}"/usr/share/icons/hicolor/512x512/apps/codetracer.png
}

