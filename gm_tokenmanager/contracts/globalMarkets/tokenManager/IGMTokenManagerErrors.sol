// SPDX-License-Identifier: BUSL-1.1
/*
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
 * @title  IGMTokenManagerErrors
 * @author Ondo Finance
 * @notice Isolated contract for all errors emitted by the GMTokenManager contract
 */
interface IGMTokenManagerErrors {
  /// Error emitted when the token address is zero
  error TokenAddressCantBeZero();

  /// Error emitted when the deposit amount is too small
  error DepositAmountTooSmall();

  /// Error emitted when the user is not registered with the ID registry
  error UserNotRegistered();

  /// Error emitted when the redemption amount is too small
  error RedemptionAmountTooSmall();

  /// Error emitted when attempting to set the `OndoIDRegistry` address to zero
  error IDRegistryAddressCantBeZero();

  /// Error emitted when attempting to set the `OndoRateLimiter` address to zero
  error RateLimiterAddressCantBeZero();

  /// Error emitted when the minting functionality is paused
  error GlobalMintsPaused();

  /// Error emitted when the redemption functionality is paused
  error GlobalRedemptionsPaused();

  /// Error emitted when the minting functionality is paused for a specific token
  error GMTokenMintsPaused();

  /// Error emitted when the redemption functionality is paused for a specific token
  error GMTokenRedemptionsPaused();

  /// Error emitted attempting to set the `OndoSanityCheckOracle` address to zero
  error SanityCheckOracleAddressCantBeZero();

  /// Custom error for expired attestations
  error AttestationExpired();

  /// Custom error for attestion signed by unverifid signer
  error InvalidAttestationSigner();

  /// Custom error for invalid chain ID
  error InvalidChainId();

  /// Custom error for invalid quote direction
  error InvalidQuoteSide();

  /// Custom error for user ID mismatch
  error UserIdMismatch(bytes32 expected, bytes32 actual);

  /// Custom error for already redeemed attestations
  error AttestationAlreadyExecuted();

  /// Error emitted when attempting to set the `IssuanceHours` address to zero
  error IssuanceHoursAddressCantBeZero();

  // Error emitted when attempting to use an USDon manager reliant function when the USDon manager is set to zero
  error USDonManagerNotEnabled();

  /// Error emitted when the GM Token is not registered for minting/redemption
  error GMTokenNotRegistered();

  /// Error emitted when attempting to set the `USDon` address to zero
  error USDonAddressCantBeZero();
}
