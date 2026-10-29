/* Two tiny helpers for reading a prediction. */

/* Did this image get a usable prediction (not missing, not an error)? */
export const okPred = im => im.prediction && !im.prediction.error;

/* The CSS class that colours a group's dot. */
export const tone = tier => `bg-${tier}`;
