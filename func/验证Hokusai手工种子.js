const hre = require('hardhat');

async function main() {
  const addresses = ['0x0000000000000000000000000000000000010000',
    '0x0000000000000000000000000000000000020000',
    '0x0000000000000000000000000000000000030000'];
  const [deployer] = await hre.ethers.getSigners();
  const harness = await (await hre.ethers.getContractFactory('EchidnaHokusaiToken', deployer)).deploy();
  await harness.waitForDeployment();
  for (const address of addresses) {
    await hre.network.provider.send('hardhat_setBalance', [address, '0x3635c9adc5dea00000']);
    await hre.network.provider.send('hardhat_impersonateAccount', [address]);
  }
  const senders = await Promise.all(addresses.map(address => hre.ethers.getSigner(address)));
  await (await harness.connect(senders[0]).mintInvestorSelf(1000000000000000000n)).wait();
  await (await harness.connect(senders[1]).mintInvestorUserA(2000000000000000000n)).wait();
  await (await harness.connect(senders[2]).burnInvestorUserA(1000000000000000000n)).wait();
  const token = await hre.ethers.getContractAt('HokusaiToken', await harness.token());
  const actual = {
    investorMinted: String(await token.investorMinted()),
    totalSupply: String(await token.totalSupply()),
    userABalance: String(await token.balanceOf('0x0000000000000000000000000000000000001001')),
    harnessBalance: String(await token.balanceOf(await harness.getAddress())),
    supplyProperty: await harness.echidna_supply_accounting(),
    investorCapProperty: await harness.echidna_investor_cap(),
  };
  console.log(JSON.stringify({senders: addresses, actual}));
  if (actual.investorMinted !== '2000000000000000001' ||
      actual.totalSupply !== '2000000000000000001' ||
      actual.userABalance !== '1000000000000000000' ||
      actual.harnessBalance !== '1000000000000000001' ||
      !actual.supplyProperty || !actual.investorCapProperty) {
    throw new Error('manual seed replay state mismatch');
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
