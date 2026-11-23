import { useEffect, useState } from "react";
import { Link } from "react-router";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { AppShell } from "../layouts/AppShell";
import {
  ApiError,
  acceptWaitlistOffer,
  cancelBooking,
  cancelWaitlist,
  listBookings,
  listWaitlist,
  type BookingView,
  type WaitlistView,
} from "../utilities/api";
import { buttonClassName, cardClassName, secondaryButtonClassName, textLinkClassName } from "../utilities/classes";
import { formatUtcRange } from "../utilities/bookableSlots";
import { resourceKindLabel } from "../utilities/resourceKind";
import { useAuth } from "../utilities/Auth";
import { usePageTitle } from "../utilities/usePageTitle";

export function BookingsPage() {
  usePageTitle("My bookings · LabLink");
  const [items, setItems] = useState<BookingView[] | null>(null);
  const [waitlist, setWaitlist] = useState<WaitlistView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [waitlistError, setWaitlistError] = useState<string | null>(null);
  const [, setDemoUser] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [cancelMessage, setCancelMessage] = useState<string | null>(null);
  const { profile } = useAuth();

  function refresh(): void {
    listBookings()
      .then((result) => {
        setItems(result.items);
        setDemoUser(result.demo_user_id);
        setError(null);
      })
      .catch((caught: unknown) => {
        setError(caught instanceof ApiError ? caught.message : "Bookings could not be loaded.");
      });
    listWaitlist()
      .then((result) => {
        setWaitlist(result.items);
        setWaitlistError(null);
      })
      .catch((caught: unknown) => {
        setWaitlistError(caught instanceof ApiError ? caught.message : "Waitlist could not be loaded.");
      });
  }

  useEffect(() => {
    refresh();
  }, [profile?.id]);

  const upcoming = (items ?? []).filter((item) => item.status === "approved" || item.status === "requested");
  const offers = (waitlist ?? []).filter((item) => item.status === "offered");

  return (
    <AppShell title="My bookings">
      <p className="max-w-2xl leading-7 text-muted">
        Upcoming bookings for your signed-in account. Cancel a time here to free it for others.
      </p>
      {cancelMessage ? (
        <p className="mt-3 text-sm text-signal" role="status">
          {cancelMessage}
        </p>
      ) : null}

      <section className="mt-8" aria-labelledby="upcoming-title">
        <h2 id="upcoming-title" className="font-display text-2xl text-primary">
          Upcoming
        </h2>
        <div className="mt-4">
          {error ? (
            <ErrorState title="Bookings unavailable" message={error} />
          ) : items === null ? (
            <LoadingState label="Loading bookings" />
          ) : upcoming.length === 0 ? (
            <EmptyState
              title="No upcoming bookings"
              description="You have no active bookings. Book a resource from the catalog."
            />
          ) : (
            <ul className="grid list-none gap-3 p-0">
              {upcoming.map((item) => (
                <li key={item.id} className={cardClassName}>
                  <p className="font-medium text-primary">{item.equipment_name ?? item.equipment_id}</p>
                  <p className="mt-1 text-sm text-muted">
                    {item.kind ? resourceKindLabel(item.kind) : null}
                    {item.purpose ? ` · ${item.purpose}` : ""}
                  </p>
                  <p className="mt-2 text-sm">{formatUtcRange(item.start, item.end)}</p>
                  <p className="mt-1 text-sm capitalize">{item.status}</p>
                  <button
                    className={`${secondaryButtonClassName} mt-3`}
                    type="button"
                    disabled={busyId === item.id}
                    onClick={() => {
                      setBusyId(item.id);
                      setCancelMessage(null);
                      cancelBooking(item.id)
                        .then(() => {
                          setCancelMessage("Booking cancelled. That time is free again.");
                          refresh();
                        })
                        .catch((caught: unknown) => {
                          setError(caught instanceof ApiError ? caught.message : "The booking could not be cancelled.");
                        })
                        .finally(() => {
                          setBusyId(null);
                        });
                    }}
                  >
                    Cancel
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="mt-10" aria-labelledby="offers-title">
        <h2 id="offers-title" className="font-display text-2xl text-primary">
          Offers
        </h2>
        <p className="mt-2 text-sm text-muted">
          Offers occupy slot locks until they expire or you accept. Accepting still revalidates
          approval and eligibility.
        </p>
        <div className="mt-4">
          {waitlistError ? (
            <ErrorState title="Offers unavailable" message={waitlistError} />
          ) : waitlist === null ? (
            <LoadingState label="Loading offers" />
          ) : offers.length === 0 ? (
            <EmptyState title="No active offers" description="There is no time-limited hold for this profile." />
          ) : (
            <ul className="grid list-none gap-3 p-0">
              {offers.map((item) => (
                <li key={item.id} className={cardClassName}>
                  <p className="font-medium text-primary">{item.equipment_id}</p>
                  <p className="mt-1 text-sm capitalize">{item.status}</p>
                  {item.offered_start && item.offered_end ? (
                    <p className="mt-2 text-sm">
                      {item.offered_start.replace("T", " ")} – {item.offered_end.replace("T", " ")}
                    </p>
                  ) : null}
                  {item.offer_expires_at ? (
                    <p className="mt-1 text-sm text-muted">Expires {item.offer_expires_at.replace("T", " ")}</p>
                  ) : null}
                  <button
                    className={`${buttonClassName} mt-3`}
                    type="button"
                    disabled={busyId === item.id}
                    onClick={() => {
                      setBusyId(item.id);
                      acceptWaitlistOffer(item.id)
                        .then(() => {
                          refresh();
                        })
                        .catch((caught: unknown) => {
                          setWaitlistError(
                            caught instanceof ApiError ? caught.message : "The offer could not be accepted.",
                          );
                        })
                        .finally(() => {
                          setBusyId(null);
                        });
                    }}
                  >
                    Accept offer
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="mt-10" aria-labelledby="waitlist-title">
        <h2 id="waitlist-title" className="font-display text-2xl text-primary">
          Waitlist
        </h2>
        <p className="mt-2 text-sm text-muted">
          Rank explanations are shown only when the API computed them. Join from an equipment page
          when no suitable slot exists.
        </p>
        <p className="mt-2 text-sm">
          <Link className={textLinkClassName} to="/equipment">
            Browse equipment
          </Link>
        </p>
        <div className="mt-4">
          {waitlistError ? (
            <ErrorState title="Waitlist unavailable" message={waitlistError} />
          ) : waitlist === null ? (
            <LoadingState label="Loading waitlist" />
          ) : waitlist.length === 0 ? (
            <EmptyState title="No waitlist entries" description="This profile has not joined a waitlist." />
          ) : (
            <ul className="grid list-none gap-3 p-0">
              {waitlist.map((item) => (
                <li key={item.id} className={cardClassName}>
                  <p className="font-medium text-primary">{item.equipment_id}</p>
                  <p className="mt-1 text-sm capitalize">{item.status}</p>
                  {item.explanation ? <p className="mt-2 text-sm leading-6">{item.explanation}</p> : null}
                  {item.rank !== null ? <p className="mt-1 text-sm text-muted">Rank {item.rank}</p> : null}
                  {item.status === "waiting" || item.status === "offered" ? (
                    <button
                      className={`${secondaryButtonClassName} mt-3`}
                      type="button"
                      disabled={busyId === item.id}
                      onClick={() => {
                        setBusyId(item.id);
                        cancelWaitlist(item.id)
                          .then(() => {
                            refresh();
                          })
                          .catch((caught: unknown) => {
                            setWaitlistError(
                              caught instanceof ApiError ? caught.message : "The waitlist entry could not be cancelled.",
                            );
                          })
                          .finally(() => {
                            setBusyId(null);
                          });
                      }}
                    >
                      Cancel waitlist
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </AppShell>
  );
}
