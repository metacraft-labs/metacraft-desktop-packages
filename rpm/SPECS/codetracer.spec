%global debug_package %{nil}
%global __strip /bin/true
%global __brp_check_rpaths %{nil}

Name:		codetracer
Version:	25.09.2
Release:	1
Summary:	A user-friendly time-traveling debugger for a variety of programming languages
License:	AGPL-3
URL:		https://codetracer.com
Source0:	https://github.com/metacraft-labs/codetracer/releases/download/%version/resources.tar.xz
Source1:	https://downloads.codetracer.com/CodeTracer-%version-amd64.AppImage
Requires:	fuse, openssl, xdg-desktop-portal

%description
A user-friendly time-travelling debugger for a variety of programming languages

%prep
tar -xf "%{SOURCE0}"

%install
install -Dm755 "%{SOURCE1}" "%{buildroot}/%{_bindir}"/ct
install -Dm644 resources/codetracer.desktop "%{buildroot}/%{_datadir}"/applications/codetracer.desktop

install -Dm644 resources/Icon.iconset/icon_16x16.png "%{buildroot}/%{_datadir}"/icons/hicolor/16x16/apps/codetracer.png
install -Dm644 resources/Icon.iconset/icon_32x32.png "%{buildroot}/%{_datadir}"/icons/hicolor/32x32/apps/codetracer.png
install -Dm644 resources/Icon.iconset/icon_128x128.png "%{buildroot}/%{_datadir}"/icons/hicolor/128x128/apps/codetracer.png
install -Dm644 resources/Icon.iconset/icon_256x256.png "%{buildroot}/%{_datadir}"/icons/hicolor/256x256/apps/codetracer.png
install -Dm644 resources/Icon.iconset/icon_512x512.png "%{buildroot}/%{_datadir}"/icons/hicolor/512x512/apps/codetracer.png

%files
%{_bindir}/ct
%{_datadir}/applications/codetracer.desktop
%{_datadir}/icons/hicolor

%changelog
* Thu Sep 25 2025 Metacraft Labs Ltd. <support@codetracer.com> - 25.09.2-1
- Hotfix release 25.09.2

* Sat Sep 20 2025 Metacraft Labs Ltd. <support@codetracer.com> - 25.09.1-1
- Release 25.09.1

* Thu Apr 10 2025 Metacraft Labs Ltd. <support@codetracer.com> - 25.03.1-1
- Initial RPM package
