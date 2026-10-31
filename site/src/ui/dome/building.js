// the architecture: dome with its slit, the pedestal, the lab gallery and the control room
import { A, C, D, HD, OX, OY, RX, RY, SLIT, W, YDC, YEQ, box, fill, floorRect, iline, px, rect, rgb, wallX, wallY } from './engine.js';

// the dome's ribs never move, so their pixels are found once
let RIBS = null;
function ribs() {
  if (RIBS) return RIBS;
  const pts = [];
  const at = (th, phi) => {
    const t = (th * Math.PI) / 180, f = (phi * Math.PI) / 180;
    pts.push(Math.floor(YEQ - 0.5 * RX * Math.cos(t) * Math.sin(f) - 0.866 * RX * Math.sin(t)) * W + Math.floor(OX + RX * Math.cos(t) * Math.cos(f)));
  };
  for (const phi of [22, 45, 68, 112, 135, 158]) for (let th = 0; th <= 90; th += 0.5) at(th, phi);
  for (let phi = 0; phi <= 180; phi += 0.4) at(38, phi);
  RIBS = new Set(pts);
  return RIBS;
}

export function drawNight() {
  fill(C('void'));
}

// the back half of the dome, cut through its centre, with the real sky in the slit
export function drawDome(sky) {
  const half = SLIT / 2;
  const top = Math.floor(YEQ - RX) - 1;
  const rib = ribs();
  for (let Y = top; Y < YDC + 9; Y++) {
    for (let X = OX - RX - 18; X <= OX + RX + 18; X++) {
      const dx = X + 0.5 - OX, cy = Y + 0.5;
      const u = dx / RX;
      if (Math.abs(u) > 1) continue;
      const s = Math.sqrt(1 - u * u);
      const ys = YEQ - RX * s, ya = YEQ - 0.866 * RX * s, ye = YEQ - RY * s, yb = YDC - RY * s;
      if (cy < ys) continue;
      const slit = Math.abs(dx) <= half;
      const rail = !slit && Math.abs(dx) <= half + 2;
      let c;
      if (cy < ye && slit) {
        const row = sky && sky[Math.floor(Y - (YEQ - RX))];
        const q = row && row[Math.floor(X - (OX - half))];
        c = q ? rgb(q[0], q[1], q[2]) : C('n1');
      } else if (cy < ya) {
        c = rail ? C('m2') : u < -0.35 ? C('d5') : u < 0.45 ? C('d4') : C('d3');
      } else if (cy < ya + 2) {
        c = rail ? C('m3') : C('x3');
      } else if (cy < ye) {
        c = rail ? C('m1') : rib.has(Y * W + X) ? C('d2') : C('d1');
      } else if (cy < yb) {
        c = cy < ye + 1 ? C('d2') : C('d0');
      } else if (cy < YDC + 4) {
        c = C('f2');
        if ((Math.floor(X + 2 * Y) & 7) === 0) c = C('f1');
        if (Math.floor(cy - yb) === 0) c = C('f0');
      } else if (cy < YDC + 8) {
        c = cy < YDC + 5 ? C('x3') : C('x1');
      } else continue;
      px(X, Y, c);
    }
  }
  // the drum's cut walls at both sides, and the shell's cut face along them
  for (const sgn of [-1, 1]) {
    const x0 = sgn < 0 ? OX - RX : OX + RX - 3;
    rect(x0, Math.floor(YEQ) - 1, 3, HD + 5, C('x2'));
    rect(sgn < 0 ? x0 + 2 : x0, Math.floor(YEQ) - 1, 1, HD + 5, C('x1'));
  }
  // red lamps on the drum
  for (const u of [-0.78, -0.42, 0.42, 0.78]) {
    const X = Math.round(OX + u * RX);
    const Y = Math.round(YEQ - RY * Math.sqrt(1 - u * u) + 3);
    rect(X - 1, Y, 3, 3, C('rd0'));
    rect(X, Y + 1, 1, 1, C('rd2'));
  }
}

// the catwalk ring around the dome, its two visible ends
export function drawCatwalk() {
  const R2 = RX + 14;
  for (let Y = YDC - 26; Y < YDC + 4; Y++) {
    for (let X = OX - R2 - 1; X <= OX + R2 + 1; X++) {
      const dx = X + 0.5 - OX, cy = Y + 0.5;
      if (Math.abs(dx) <= RX || Math.abs(dx) > R2) continue;
      const s = Math.sqrt(Math.max(0, 1 - (dx / R2) ** 2));
      if (cy < YDC - (R2 / 2) * s) continue;
      if (cy < YDC) px(X, Y, Math.floor(X) % 3 === 0 ? C('m1') : C('m2'));
      else if (cy < YDC + 3) px(X, Y, C('x2'));
    }
  }
}

export function drawCatwalkRail() {
  const R2 = RX + 14;
  for (const sgn of [-1, 1]) {
    for (let X = RX + 1; X <= R2; X++) {
      const s = Math.sqrt(Math.max(0, 1 - ((X + 0.5) / R2) ** 2));
      const yo = Math.floor(YDC - (R2 / 2) * s);
      const x = OX + sgn * X - (sgn < 0 ? 1 : 0);
      px(x, yo - 9, C('m3'));
      px(x, yo - 5, C('m1'));
      if (X % 4 === 0) for (let k = 1; k < 9; k++) px(x, yo - k, C('m2'));
    }
    // the rail's end post at the cut
    const xe = OX + sgn * R2 - (sgn < 0 ? 0 : 1);
    for (let k = 0; k < 10; k++) px(xe, YDC - k, C('m3'));
  }
}

// the solid section under the dome floor, between the floor's cut and the roof line
export function drawPedestal() {
  for (let X = OX - RX; X < OX + RX; X++) {
    const roof = OY - 112 + Math.abs(X + 0.5 - OX) / 2;
    for (let Y = YDC + 8; Y < roof; Y++) {
      let c = C('x1');
      if ((Y - YDC) % 7 === 0) c = C('x0');
      if (Y === YDC + 8) c = C('x2');
      px(X, Y, c);
    }
  }
  // brackets under the catwalk
  for (const sgn of [-1, 1]) {
    for (let k = 0; k < 12; k++) px(OX + sgn * (RX + 12 - k) - (sgn > 0 ? 1 : 0), YDC + 3 + k, C('m1'));
  }
}

// walls with seams, a rail and a skirting, between floor z0 and ceiling z1
function wallsAt(z0, z1) {
  wallX(0, 0, A, z0, z1, C('w2'));
  wallY(0, 0, A, z0, z1, C('w1'));
  wallX(0, 0, A, z0, z0 + 3, C('w0'));
  wallY(0, 0, A, z0, z0 + 3, C('w0'));
  iline([0, 0, z0 + 22], [0, A, z0 + 22], C('w3'));
  iline([0, 0, z0 + 22], [A, 0, z0 + 22], C('w0'));
  for (let i = 2; i < A; i += 2) {
    iline([0, i, z0 + 3], [0, i, z1 - 1], C('w1'));
    iline([i, 0, z0 + 3], [i, 0, z1 - 1], C('w0'));
  }
  iline([0, 0, z0], [0, 0, z1], C('w3'));
}

export function wallTops(z) {
  floorRect(-0.5, -0.5, 0, A, z, C('w4'));
  floorRect(-0.5, -0.5, A, 0, z, C('w4'));
  iline([0, 0, z], [0, A, z], C('w5'));
  iline([0, 0, z], [A, 0, z], C('w5'));
}

// floor tiles: base colour and seams every two tiles
function tiles(x0, y0, x1, y1, z, base, seam) {
  floorRect(x0, y0, x1, y1, z, base);
  for (let x = Math.ceil(x0 / 2) * 2; x <= x1; x += 2) if (x > x0 && x < x1) iline([x, y0, z], [x, y1, z], seam);
  for (let y = Math.ceil(y0 / 2) * 2; y <= y1; y += 2) if (y > y0 && y < y1) iline([x0, y, z], [x1, y, z], seam);
}

// the ends of the building where the front walls were cut away
function cutEnds(z0, z1) {
  wallY(A, -0.5, 0, z0, z1, C('x2'));
  wallX(A, -0.5, 0, z0, z1, C('x2'));
}

export function drawControlShell() {
  wallsAt(0, 52);
  tiles(0, 0, A, A, 0, C('f1'), C('f0'));
  // the floor slab's cut faces at the front edges
  wallY(A, 0, A, -5, 0, C('x1'));
  wallX(A, 0, A, -5, 0, C('x0'));
  iline([0, A, 0], [A, A, 0], C('x3'));
  iline([A, 0, 0], [A, A, 0], C('x2'));
  cutEnds(0, 52);
}

// H-alpha red lamps: dim, until the sky misses the forecast and Le Verrier is woken
export function drawLabShell(alarm) {
  wallsAt(56, 112);
  const on = alarm ? C('rd2') : C('rd0');
  for (const k of [11, 24]) {
    box(-0.25, k, 96, 0.25, 0.6, 4, C('x0'), on, C('x0'));
    box(k, -0.25, 96, 0.6, 0.25, 4, C('x0'), C('x0'), on);
  }
  // a cable tray from the telescope's corner along both walls, feeding every station
  box(0, 0, 103, 0.7, A, 2, C('m2'), C('m1'), C('m1'));
  box(0.7, 0, 103, A - 0.7, 0.7, 2, C('m2'), C('m1'), C('m1'));
  for (let k = 3; k < A; k += 3) {
    iline([0.35, k, 103], [0.05, k, 107], C('m1'));
    iline([k, 0.35, 103], [k, 0.05, 107], C('m1'));
  }
}

export function drawGalleryFloor() {
  tiles(0, 0, D, A, 56, C('f2'), C('f1'));
  tiles(D, 0, A, D, 56, C('f2'), C('f1'));
  // the slab's cut faces along the gallery edge and at both ends
  wallX(D, D, A, 51, 56, C('x1'));
  wallY(D, D, A, 51, 56, C('x0'));
  iline([D, D, 56], [D, A, 56], C('x3'));
  iline([D, D, 56], [A, D, 56], C('x2'));
  wallY(A, 0, D, 51, 56, C('x2'));
  wallX(A, 0, D, 51, 56, C('x2'));
  cutEnds(56, 112);
}

// the railing along the gallery edge
export function drawRailing() {
  const z = 56;
  for (let y = D; y <= A; y += 1) iline([D, y, z], [D, y, z + 9], C('m2'));
  for (let x = D + 1; x <= A; x += 1) iline([x, D, z], [x, D, z + 9], C('m2'));
  iline([D, D, z + 9], [D, A, z + 9], C('m4'));
  iline([D, D, z + 9], [A, D, z + 9], C('m4'));
  iline([D, D, z + 5], [D, A, z + 5], C('m1'));
  iline([D, D, z + 5], [A, D, z + 5], C('m1'));
}

