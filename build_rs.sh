#!/bin/bash
set -e

unset BINDGEN_EXTRA_CLANG_ARGS
unset SDKROOT

echo "1. Generating Dart glue code..."
cd frontend
flutter_rust_bridge_codegen generate
cd ..

cd native_ffi

echo "2. Compiling Rust for macOS Apple Silicon..."
cargo build --release --target aarch64-apple-darwin

echo "3. Building Rust for Physical iPhone/iPad..."
cargo build --release --target aarch64-apple-ios

# If you also want iOS Simulator support:
cargo build --release --target aarch64-apple-ios-sim
cd ..

echo "4. Copying compiled binary into Flutter frontend..."

cp native_ffi/target/aarch64-apple-ios-sim/release/libnative_ffi.a frontend/ios/libnative_ffi_sim.a
cp native_ffi/target/aarch64-apple-ios/release/libnative_ffi.a frontend/ios/libnative_ffi.a
cp native_ffi/target/aarch64-apple-ios/release/libnative_ffi.a frontend/ios/libnative_ffi_desktop.a


echo "Done! Rust backend updated and copied to frontend."
