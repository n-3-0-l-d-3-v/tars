export function greet(name) {
  return `Hello, ${name}! This is __TARS_PROJECT_NAME__.`;
}

function main() {
  const name = process.argv[2] || "World";
  console.log(greet(name));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}
