# Historical Qt sidebar regression before V114 reflow repair

Source: `fix/v114-main-jss-runtime-recovery-20261108`, base code derived from `checks/jazn_latka_v113_test` commit `6bf83222c45575a4e83b4cc7ff326fcba4f34b3c`.

This archive preserves the existing active test byte-for-byte before adding a responsive-reflow assertion. The original assertion expected `＋ Nowa rozmowa`; the generic VisualSystem.reflow() could split this into two lines. The patch preserves the action label while keeping automatic wrapping for other buttons.
