`include "defs.svh"

module pass_with_include(
  input  logic a,
  input  logic b,
  output logic y
);
  always_comb begin
    y = a `AND_OP b;
  end
endmodule
