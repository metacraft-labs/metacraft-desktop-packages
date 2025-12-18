# Distributed under the terms of the MIT License

EAPI="8"

DESCRIPTION="RR backend support for CodeTracer time-traveling debugger"
HOMEPAGE="https://codetracer.com"
SRC_URI="https://downloads.codetracer.com/CodeTracer-RR-Backend-${PV}-amd64.AppImage -> ct-rr-support"

LICENSE="all-rights-reserved"
SLOT="0"
KEYWORDS="*"
IUSE=""
RESTRICT="strip" # Stripping will make the AppImage unable to run

BDEPEND=""
DEPEND=""
RDEPEND="sys-fs/fuse
	dev-libs/openssl
	dev-debug/codetracer-bin
"

S="${WORKDIR}/"

src_unpack() {
	cp "${DISTDIR}"/ct-rr-support "${WORKDIR}"
}

src_install() {
	dobin "${WORKDIR}"/ct-rr-support
}
