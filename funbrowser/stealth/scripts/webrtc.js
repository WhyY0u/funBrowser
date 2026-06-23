// Block WebRTC from emitting ICE candidates with the host's real IP.
// The launch flag --force-webrtc-ip-handling-policy=disable_non_proxied_udp does the
// heavy lifting at the network layer, but a JS-level wrap on the connection
// objects keeps the API answers consistent if a script tries to introspect them.
(() => {
  if (typeof RTCPeerConnection === 'undefined') return;

  const proto = RTCPeerConnection.prototype;
  const origCreateDC = proto.createDataChannel;
  const origCreateOffer = proto.createOffer;
  const origCreateAnswer = proto.createAnswer;
  const origSetLocal = proto.setLocalDescription;
  const origGetStats = proto.getStats;

  // Filter the SDP returned by createOffer / createAnswer so non-proxied
  // host candidates are stripped before the page ever sees the address.
  const filterSDP = (desc) => {
    if (!desc || typeof desc.sdp !== 'string') return desc;
    const out = desc.sdp
      .split('\n')
      .filter((l) => !/^a=candidate:.* (host|srflx) /i.test(l))
      .join('\n');
    return Object.assign({}, desc, { sdp: out });
  };

  proto.createOffer = window.__fb_m(function () {
    return origCreateOffer.apply(this, arguments).then(filterSDP);
  }, 'createOffer');

  proto.createAnswer = window.__fb_m(function () {
    return origCreateAnswer.apply(this, arguments).then(filterSDP);
  }, 'createAnswer');

  proto.setLocalDescription = window.__fb_m(function (desc) {
    return origSetLocal.call(this, filterSDP(desc));
  }, 'setLocalDescription');

  proto.createDataChannel = window.__fb_m(function () {
    return origCreateDC.apply(this, arguments);
  }, 'createDataChannel');

  proto.getStats = window.__fb_m(function () {
    return origGetStats.apply(this, arguments);
  }, 'getStats');
})();
