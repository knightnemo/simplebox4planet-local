# Third-party model and data

The `SimpleBox4Planet` Git submodule points to the publicly released NovaMechanics SimpleBox4Planet repository:

- Repository: https://github.com/NovaMechanicsOpenSource/SimpleBox4Planet
- Pinned commit: `297dfacb633afc8140760b754360b3ff5a7d83c6`
- License: Apache License 2.0, preserved in `SimpleBox4Planet/LICENSE`
- Underlying model: RIVM SimpleBox version 4.04

The original model files remain unchanged. Runtime copies receive user inputs and two documented lake-emission connections (`engine!E5` and `engine!N5`); formula caches are cleared before local recalculation. The standalone frontend, HTTP API, dynamic solver and fate-factor presentation are independent additions.

This project is not affiliated with or endorsed by NovaMechanics, RIVM or the operators of the hosted SimpleBox4Planet service. Refer to the upstream README for model references and author citation.
