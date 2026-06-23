(() => {
  // Tiny sub-audible noise on audio readouts. Same goal as canvas noise:
  // break fingerprint hashes without making the audio unusable for real apps.
  const EPS = 1e-7;

  const orig = AudioBuffer.prototype.getChannelData;
  AudioBuffer.prototype.getChannelData = function (...args) {
    const data = orig.apply(this, args);
    for (let i = 0; i < data.length; i++) {
      data[i] += (Math.random() - 0.5) * EPS;
    }
    return data;
  };

  if (AudioBuffer.prototype.copyFromChannel) {
    const origCopy = AudioBuffer.prototype.copyFromChannel;
    AudioBuffer.prototype.copyFromChannel = function (dest, ...rest) {
      origCopy.call(this, dest, ...rest);
      for (let i = 0; i < dest.length; i++) {
        dest[i] += (Math.random() - 0.5) * EPS;
      }
    };
  }

  const origFreq = AnalyserNode.prototype.getFloatFrequencyData;
  AnalyserNode.prototype.getFloatFrequencyData = function (array) {
    origFreq.call(this, array);
    for (let i = 0; i < array.length; i++) {
      array[i] += (Math.random() - 0.5) * EPS;
    }
  };
})();
