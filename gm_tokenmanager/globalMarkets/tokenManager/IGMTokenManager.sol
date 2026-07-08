/**SPDX-License-Identifier: BUSL-1.1

      ▄▄█████████▄
   ╓██▀└ ,╓▄▄▄, '▀██▄
  ██▀ ▄██▀▀╙╙▀▀██▄ └██µ           ,,       ,,      ,     ,,,            ,,,
 ██ ,██¬ ▄████▄  ▀█▄ ╙█▄      ▄███▀▀███▄   ███▄    ██  ███▀▀▀███▄    ▄███▀▀███,
██  ██ ╒█▀'   ╙█▌ ╙█▌ ██     ▐██      ███  █████,  ██  ██▌    └██▌  ██▌     └██▌
██ ▐█▌ ██      ╟█  █▌ ╟█     ██▌      ▐██  ██ └███ ██  ██▌     ╟██ j██       ╟██
╟█  ██ ╙██    ▄█▀ ▐█▌ ██     ╙██      ██▌  ██   ╙████  ██▌    ▄██▀  ██▌     ,██▀
 ██ "██, ╙▀▀███████████⌐      ╙████████▀   ██     ╙██  ███████▀▀     ╙███████▀`
  ██▄ ╙▀██▄▄▄▄▄,,,                ¬─                                    '─¬
   ╙▀██▄ '╙╙╙▀▀▀▀▀▀▀▀
      ╙▀▀██████R⌐

 */

pragma solidity 0.8.16;

/**
 * @title  IGMTokenManager
 * @author Ondo Finance
 * @notice Interface for interacting with the GMTokenManager contract
 */
interface IGMTokenManager {
  enum QuoteSide {
    /// Indicates that the user is buying GM tokens
    BUY,
    /// Indicates that the user is selling GM tokens
    SELL
  }

  /**
   * @notice Quote struct that is signed by the attestation signer
   * @param  attestationId  The ID of the quote
   * @param  chainId        The chain ID of the quote is intended for
   * @param  userId         The user ID the quote is intended for
   * @param  asset          The address of the GM token being bought or sold
   * @param  price          The price of the GM token in USD with 18 decimals
   * @param  quantity       The quantity of GM tokens being bought or sold
   * @param  expiration     The expiration of the quote in seconds since the epoch
   * @param  side           The direction of the quote (BUY or SELL)
   * @param  additionalData Any additional data that is needed for the quote
   */
  struct Quote {
    uint256 chainId;
    uint256 attestationId;
    bytes32 userId;
    address asset;
    uint256 price;
    uint256 quantity;
    uint256 expiration;
    QuoteSide side;
    bytes32 additionalData;
  }

  /**
   * @notice Event emitted when a trade is executed with an attestation
   * @param  executionId    The monotonically increasing ID of the trade
   * @param  attestationId  The ID of the quote
   * @param  chainId        The chain ID the quote is intended to be used
   * @param  userId         The user ID the quote is intended for
   * @param  side           The direction of the quote (BUY or SELL)
   * @param  asset          The address of the GM token being bought or sold
   * @param  price          The price of the GM token in USD with 18 decimals
   * @param  quantity       The quantity of GM tokens being bought or sold
   * @param  expiration     The expiration of the quote in seconds since the epoch
   * @param  additionalData Any additional data that is needed for the quote
   */
  event TradeExecuted(
    uint256 executionId,
    uint256 attestationId,
    uint256 chainId,
    bytes32 userId,
    QuoteSide side,
    address asset,
    uint256 price,
    uint256 quantity,
    uint256 expiration,
    bytes32 additionalData
  );

  function mintWithAttestation(
    Quote calldata quote,
    bytes memory signature,
    address depositToken,
    uint256 depositAmount
  ) external returns (uint256 receivedGmTokenAmount);

  function redeemWithAttestation(
    Quote calldata quote,
    bytes memory signature,
    address receiveToken,
    uint256 minimumReceiveAmount
  ) external returns (uint256 redemptionUSDonValue);
}
