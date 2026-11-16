# Third-party sources

## Three.js

Three.js r180 (MIT), copyright Three.js authors. The original MIT notice is retained at [LICENSE-three.txt](airpresent/viewer3d/web/vendor/LICENSE-three.txt). Vendored file URLs and SHA256 hashes are in [manifest.json](airpresent/viewer3d/web/vendor/manifest.json).

## MediaPipe / Hand Landmarker

Hand tracking uses the upstream MediaPipe package. Model weights are downloaded by setup.bat from the fixed official source and are not redistributed in this repository. See [models/README.md](models/README.md) and the [official Hand Landmarker documentation](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker). Upstream package/model terms apply.

## Other runtime packages

OpenCV, NumPy, Pillow and pywin32 are installed as dependencies; their upstream licenses apply. They are not vendored here.

## Design and implementation references

[VIEWER3D_REFERENCES.md](VIEWER3D_REFERENCES.md) records the repositories, inspected commits, ideas adopted and decisions changed. The viewer/controller code was independently implemented; demonstration models from those repositories were not copied. The built-in optical assembly is generated procedurally by this project.

This notice identifies upstream materials and does not grant a new license for the project's own code.
