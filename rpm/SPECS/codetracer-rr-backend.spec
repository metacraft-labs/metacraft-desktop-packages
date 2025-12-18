%global debug_package %{nil}
%global __strip /bin/true
%global __brp_check_rpaths %{nil}

Name:		codetracer-rr-backend
Version:	0.1.0
Release:	1
Summary:	RR backend support for CodeTracer time-traveling debugger
License:	Proprietary
URL:		https://codetracer.com
Source0:	https://downloads.codetracer.com/CodeTracer-RR-Backend-%version-amd64.AppImage
Requires:	fuse, fuse-libs, openssl, codetracer

%description
RR backend support for CodeTracer - enables recording and debugging of C, C++, Rust, Go and other compiled languages using the rr time-traveling debugger.

%install
install -Dm755 "%{SOURCE0}" "%{buildroot}/%{_bindir}"/ct-rr-support

%files
%{_bindir}/ct-rr-support

%changelog
* Mon Dec 16 2024 Metacraft Labs Ltd. <support@codetracer.com> - 0.1.0-1
- Initial RPM package for RR backend
