export {};

declare global {
  interface WebTransportCloseInfo {
    closeCode?: number;
    reason?: string;
  }

  interface WebTransportOptions {
    allowPooling?: boolean;
    requireUnreliable?: boolean;
    serverCertificateHashes?: WebTransportHash[];
  }

  interface WebTransportHash {
    algorithm: string;
    value: BufferSource;
  }

  interface WebTransport {
    readonly closed: Promise<WebTransportCloseInfo>;
    readonly ready: Promise<void>;
    createBidirectionalStream(): Promise<WebTransportBidirectionalStream>;
    close(closeInfo?: WebTransportCloseInfo): void;
  }

  interface WebTransportBidirectionalStream {
    readonly readable: ReadableStream<Uint8Array>;
    readonly writable: WritableStream<Uint8Array>;
  }

  var WebTransport: {
    prototype: WebTransport;
    new (url: string, options?: WebTransportOptions): WebTransport;
  };
}
