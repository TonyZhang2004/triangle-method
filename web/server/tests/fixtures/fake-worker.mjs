import process from "node:process";

function gcd(left, right) {
  let first = left < 0n ? -left : left;
  let second = right;
  while (second !== 0n) {
    [first, second] = [second, first % second];
  }
  return first;
}

function rationalRecord(value) {
  const [rawNumerator, rawDenominator = "1"] = value.split("/");
  let numerator = BigInt(rawNumerator);
  let denominator = BigInt(rawDenominator);
  const divisor = gcd(numerator, denominator);
  numerator /= divisor;
  denominator /= divisor;
  return { numerator: String(numerator), denominator: String(denominator) };
}

function successResponse(request) {
  return {
    schema: "triangle_method.proof_response",
    schemaVersion: 1,
    outcome: "PROVED",
    method: "zero",
    target: {
      degree: request.degree,
      coefficientRows: request.coefficientRows.map((row) =>
        row.map(rationalRecord),
      ),
      latex: "0 \\ge 0",
    },
    proof: {
      verified: true,
      residualZero: true,
      identityLatex: "0 = 0 \\ge 0",
      terms: [],
      steps: [],
      groups: [],
    },
    counterexample: null,
    diagnostics: [{ code: "zero.matched", message: "The target is zero." }],
  };
}

const mode = process.argv[2] ?? "success";
let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  input += chunk;
});
process.stdin.on("end", () => {
  if (mode === "hang") {
    setInterval(() => {}, 1000);
    return;
  }
  if (mode === "stdout-limit") {
    process.stdout.write("x".repeat(4096));
    return;
  }
  if (mode === "stderr-limit") {
    process.stderr.write("x".repeat(4096));
    return;
  }
  if (mode === "failure") {
    process.stderr.write('{"error":{"code":"test","message":"failed"}}\n');
    process.exitCode = 2;
    return;
  }
  if (mode === "bad-json") {
    process.stdout.write("not json\n");
    return;
  }
  const request = JSON.parse(input);
  const response = successResponse(request);
  if (mode === "mismatch") {
    response.target.coefficientRows[0][0] = {
      numerator: "1",
      denominator: "1",
    };
  }
  if (mode === "invalid-contract") {
    delete response.proof.residualZero;
  }
  process.stdout.write(`${JSON.stringify(response)}\n`);
});
